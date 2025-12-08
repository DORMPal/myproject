import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterOutlet } from '@angular/router';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-login',
  imports: [CommonModule, RouterOutlet, FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class Login {}
