import { CommonModule } from '@angular/common';
import { Component, Input, OnInit, OnDestroy, ChangeDetectorRef, NgZone } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService, NotificationItem, NotificationResponse } from '../../services/api.service';
import { BadgeModule } from 'primeng/badge';
import { OverlayBadgeModule } from 'primeng/overlaybadge';
import { DrawerModule } from 'primeng/drawer';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api'; // ✅ เพิ่ม MessageService
import { ToastModule } from 'primeng/toast';

type HeaderTab = 'recipes' | 'ingredients' | '';
interface Name {
  email: string;
  id: number;
  name: string;
}

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    BadgeModule,
    OverlayBadgeModule,
    DrawerModule,
    ButtonModule,
    TooltipModule,
    ToastModule,
  ],
  providers: [MessageService], // ✅ เพิ่ม MessageService ใน providers
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent implements OnInit, OnDestroy {
  @Input() active: HeaderTab = '';
  nums_notifications: number = 0;
  toggle_notifications: boolean = false;
  notifications: NotificationItem[] = [];
  sidebarVisible: boolean = false;

  recognition: any = null;
  isListening: boolean = false;
  voiceText: string = '';

  constructor(
    private readonly router: Router,
    private readonly api: ApiService,
    private messageService: MessageService, // ✅ Inject MessageService
    private ngZone: NgZone
  ) {}

  name: Name = null as any;

  ngOnInit(): void {
    // ✅ ย้ายการเช็ค User ไปไว้หลังสุด หรือแยก function เพื่อไม่ให้กวนการ test เสียง
    this.checkUserLogin();
  }

  ngOnDestroy(): void {
    if (this.recognition) {
      this.recognition.stop();
    }
  }

  checkUserLogin() {
    this.api.getCurrentUser().subscribe({
      next: (user) => {
        console.log('current user', user);
        this.name = user;
        console.log('name', this.name);
        // Load notifications after successful login
        this.loadNotifications();
      },
      error: () => {
        // อยู่หน้า Login ต่อไป
      },
    });
  }

  loadNotifications() {
    this.api.getNotifications().subscribe({
      next: (response: NotificationResponse) => {
        this.notifications = response.notifications;
        this.nums_notifications = response.unread_count;
      },
      error: (error) => {
        console.error('Error loading notifications:', error);
      },
    });
  }

  markAsRead(notificationId: number) {
    this.api.markNotificationAsRead(notificationId).subscribe({
      next: () => {
        // Update the notification in the local array
        const notification = this.notifications.find((n) => n.id === notificationId);
        if (notification) {
          notification.read_yet = true;
          // Decrease the unread count
          if (this.nums_notifications > 0) {
            this.nums_notifications--;
          }
        }
      },
      error: (error) => {
        console.error('Error marking notification as read:', error);
      },
    });
  }

  logout(): void {
    this.api.logout().subscribe({
      next: (response) => {
        console.log('Logout successful:', response);
        localStorage.removeItem('token');
        this.name = null as any;
        this.router.navigateByUrl('/login');
      },
      error: (error) => {
        console.error('Logout error:', error);
        // Even if there's an error, we should still clear local storage and redirect
        localStorage.removeItem('token');
        this.name = null as any;
        this.router.navigateByUrl('/login');
      },
    });
  }

  closeSidebar() {
    this.sidebarVisible = false;
  }

  toggleSpeech() {
    if (this.isListening) {
      this.stopListening();
    } else {
      this.startListening();
    }
  }

  startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Browser นี้ไม่รองรับการสั่งงานด้วยเสียง',
      });
      return;
    }

    // Init แค่ครั้งเดียว
    if (!this.recognition) {
      this.recognition = new SpeechRecognition();
      this.recognition.lang = 'th-TH';
      this.recognition.continuous = false; // ให้มันหยุดเองเมื่อพูดจบประโยค หรือรอเรากดหยุด
      this.recognition.interimResults = false;

      this.recognition.onstart = () => {
        // ✅ ใช้ ngZone.run เพื่อให้ Angular รู้ว่าตัวแปรเปลี่ยน (Update UI ทันที)
        this.ngZone.run(() => {
          this.isListening = true;
          this.voiceText = 'กำลังฟัง...';
          console.log('🎙️ Started listening');
        });
      };

      this.recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        this.ngZone.run(() => {
          this.voiceText = transcript;
          console.log('🗣️ Transcript:', transcript);
          // เรียก API ทันทีที่พูดจบ
          this.processVoiceCommand(transcript);
        });
      };

      this.recognition.onerror = (event: any) => {
        this.ngZone.run(() => {
          console.error('Speech Error:', event.error);
          this.isListening = false;
          this.voiceText = '';
          // แจ้งเตือน Error เล็กน้อยถ้าไม่ใช่การกดปิดเอง
          if (event.error !== 'no-speech' && event.error !== 'aborted') {
            this.messageService.add({
              severity: 'error',
              summary: 'Microphone Error',
              detail: event.error,
            });
          }
        });
      };

      this.recognition.onend = () => {
        this.ngZone.run(() => {
          this.isListening = false;
          console.log('🛑 Stopped listening');
        });
      };
    }

    this.recognition.start();
  }

  stopListening() {
    if (this.recognition) {
      this.recognition.stop();
      this.isListening = false;
    }
  }

  processVoiceCommand(text: string) {
    if (!text) return;

    // 1. แจ้งเตือนว่ากำลังส่งข้อมูล
    this.messageService.add({
      severity: 'info',
      summary: 'กำลังประมวลผล...',
      detail: `"${text}"`,
      life: 3000,
    });

    // 2. เรียก API
    this.api.sendVoiceCommand(text).subscribe({
      next: (res: any) => {
        // 3. สำเร็จ: แสดงข้อความจาก Backend (เช่น "เพิ่มไข่ไก่ 3 ฟอง เรียบร้อย")
        if (res.success) {
          this.messageService.add({
            severity: 'success',
            summary: 'สำเร็จ',
            detail: res.message,
            life: 5000,
          });

          // Optional: ถ้าอยากให้ Notification อัปเดตด้วย (กรณีมีแจ้งเตือนของใกล้หมดอายุที่ถูกเพิ่มเข้ามาใหม่)
          // this.loadNotifications();
        } else {
          // กรณี Backend ตอบกลับมาแต่ success = false (เช่น หาของไม่เจอ)
          this.messageService.add({
            severity: 'warn',
            summary: 'ตรวจสอบข้อมูล',
            detail: res.message,
          });
        }
      },
      error: (err) => {
        // 4. ผิดพลาด: แจ้งเตือน Error
        console.error('API Error:', err);
        const errorMsg = err.error?.message || 'ระบบขัดข้อง กรุณาลองใหม่';
        this.messageService.add({ severity: 'error', summary: 'ผิดพลาด', detail: errorMsg });
      },
    });
  }
}
