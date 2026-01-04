import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { HttpClient } from '@angular/common/http'; // เพิ่ม HttpClient
import { ApiService } from '../services/api.service';

@Component({
  selector: 'app-login',
  standalone: true, // ✅ เพิ่ม standalone: true (ถ้าใช้ Angular 14+ แบบ Standalone Component)
  imports: [CommonModule, RouterOutlet, FormsModule, ButtonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit, OnDestroy {
  isRecording: boolean = false;
  transcript: string = '';
  aiResponse: string = '';
  private recognition: any;
  readonly googleLoginUrl = 'http://localhost:8000/auth/google/login/';

  constructor(
    private readonly api: ApiService,
    private readonly router: Router,
    private http: HttpClient,
    private cdr: ChangeDetectorRef
  ) {}

  ngOnInit(): void {
    // ✅ ย้ายการเช็ค User ไปไว้หลังสุด หรือแยก function เพื่อไม่ให้กวนการ test เสียง
    this.checkUserLogin();
    this.initSpeechRecognition();
  }

  ngOnDestroy() {
    if (this.recognition) {
      this.recognition.abort();
    }
  }

  checkUserLogin() {
    this.api.getCurrentUser().subscribe({
      next: (user) => {
        console.log('current user', user);
        localStorage.setItem('token', 'session');
        this.router.navigateByUrl('/page/ingredient');
      },
      error: () => {
        // อยู่หน้า Login ต่อไป
      },
    });
  }

  login(): void {
    window.location.href = this.googleLoginUrl;
  }

  initSpeechRecognition() {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) {
      alert('Browser นี้ไม่รองรับการสั่งงานด้วยเสียง (แนะนำ Google Chrome)');
      return;
    }

    this.recognition = new SpeechRecognition();
    this.recognition.lang = 'th-TH';
    this.recognition.continuous = true;
    this.recognition.interimResults = true;

    // ✅ แก้ไขส่วน onresult: ให้เก็บข้อความทั้งหมดตั้งแต่เริ่มพูด
    this.recognition.onresult = (event: any) => {
      let fullTranscript = '';

      // วนลูปจาก 0 เสมอ เพื่อประกอบร่างประโยคใหม่ทั้งหมดใน Session นี้
      for (let i = 0; i < event.results.length; i++) {
        fullTranscript += event.results[i][0].transcript;
      }

      this.transcript = fullTranscript;
      this.cdr.detectChanges(); // บังคับหน้าจออัปเดต
    };

    // กรณี Browser หยุดเอง (เงียบ/Error)
    this.recognition.onend = () => {
      if (this.isRecording) {
        console.warn('Microphone stopped automatically.');
        this.isRecording = false;

        // ถ้ามีข้อความค้างอยู่ ให้ลองส่งเลยไหม? หรือแค่หยุดเฉยๆ
        if (this.transcript.trim()) {
          console.log('Auto-sending due to stop:', this.transcript);
          // this.sendToBackend(); // เปิดบรรทัดนี้ถ้าอยากให้ส่งอัตโนมัติเมื่อหยุดพูด
        }

        this.cdr.detectChanges();
      }
    };

    this.recognition.onerror = (event: any) => {
      console.error('Speech Error:', event.error);
      this.isRecording = false;
      this.cdr.detectChanges();
    };
  }

  toggleRecording() {
    if (this.isRecording) {
      // 🛑 สั่งหยุด
      this.recognition.stop();
      this.isRecording = false;

      // ส่งข้อความเมื่อกดหยุด
      if (this.transcript.trim()) {
        console.log('Finishing command:', this.transcript);
        // this.sendToBackend(this.transcript); // ✅ เรียกฟังก์ชันส่ง
      }
    } else {
      // ▶️ สั่งเริ่ม
      this.transcript = '';
      this.aiResponse = '';
      this.recognition.start();
      this.isRecording = true;
    }
  }

  // ✅ ฟังก์ชันส่งข้อมูลไป Backend
}
