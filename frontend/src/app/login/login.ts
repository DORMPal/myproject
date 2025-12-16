import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterOutlet } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../services/api.service';

@Component({
  selector: 'app-login',
  imports: [CommonModule, RouterOutlet, FormsModule, ButtonModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login implements OnInit {
  readonly googleLoginUrl = 'http://localhost:8000/auth/google/login/';

  constructor(private readonly api: ApiService, private readonly router: Router) {}

  ngOnInit(): void {
    // If already logged in (session cookie present), set marker and redirect
    this.api.getCurrentUser().subscribe({
      next: (user) => {
        console.log('current user', user);
        localStorage.setItem('token', 'session');
        this.router.navigateByUrl('/page/ingredient');
      },
      error: () => {
        // stay on login
      },
    });
  }

  login(): void {
    window.location.href = this.googleLoginUrl;
  }
}
