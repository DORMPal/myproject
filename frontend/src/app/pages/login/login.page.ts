import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface QuickStat {
  label: string;
  value: string;
  hint: string;
}

@Component({
  selector: 'app-login-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './login.page.html',
  styleUrls: ['./login.page.scss'],
})
export class LoginPageComponent {
  credentials = {
    email: '',
    password: '',
    staySignedIn: true,
  };

  quickStats: QuickStat[] = [
    { label: 'Pantry items', value: '18', hint: '+3 this week' },
    { label: 'Ready-to-cook dishes', value: '7', hint: 'Based on your pantry' },
    { label: 'Expiring soon', value: '4', hint: 'Use within 3 days' },
  ];

  submit(): void {
    // Placeholder action for the mock login flow.
    console.log('Mock login attempt', this.credentials);
  }
}
