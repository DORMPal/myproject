import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService, NotificationItem, NotificationResponse } from '../../services/api.service';
import { BadgeModule } from 'primeng/badge';
import { OverlayBadgeModule } from 'primeng/overlaybadge';
import { DrawerModule } from 'primeng/drawer';
import { ButtonModule } from 'primeng/button';

type HeaderTab = 'recipes' | 'ingredients' | '';
interface Name {
  email: string;
  id: number;
  name: string;
}

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, RouterLink, BadgeModule, OverlayBadgeModule, DrawerModule, ButtonModule],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  @Input() active: HeaderTab = '';
  nums_notifications: number = 0;
  toggle_notifications: boolean = false;
  notifications: NotificationItem[] = [];
  sidebarVisible: boolean = false;

  constructor(private readonly router: Router, private readonly api: ApiService) {}

  name: Name = null as any;

  ngOnInit(): void {
    // ✅ ย้ายการเช็ค User ไปไว้หลังสุด หรือแยก function เพื่อไม่ให้กวนการ test เสียง
    this.checkUserLogin();
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
}
