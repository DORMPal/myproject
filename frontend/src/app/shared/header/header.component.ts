import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../services/api.service';

type HeaderTab = 'recipes' | 'ingredients' | '';
interface Name {
  email: string;
  id: number;
  name: string;
}

@Component({
  selector: 'app-header',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './header.component.html',
  styleUrl: './header.component.scss',
})
export class HeaderComponent {
  @Input() active: HeaderTab = '';
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
      },
      error: () => {
        // อยู่หน้า Login ต่อไป
      },
    });
  }

  logout(): void {
    localStorage.removeItem('token');
    this.router.navigateByUrl('/login');
  }
}
