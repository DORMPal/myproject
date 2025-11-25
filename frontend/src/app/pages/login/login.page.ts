import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

interface QuickStat {
  label: string;
  value: string;
  hint: string;
}

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './login.page.html',
  styleUrls: ['./login.page.scss'],
})
export class LoginPageComponent {
  // Point directly to the Django backend Google OAuth endpoint.
  readonly googleLoginUrl = 'http://localhost:8000/auth/google/login/';

  quickStats: QuickStat[] = [
    { label: 'Pantry items', value: '18', hint: '+3 this week' },
    { label: 'Ready-to-cook dishes', value: '7', hint: 'Based on your pantry' },
    { label: 'Expiring soon', value: '4', hint: 'Use within 3 days' },
  ];
}
