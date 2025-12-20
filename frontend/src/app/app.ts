import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { IngredientsStore } from './core/ingredients.store';
import { HttpClient } from '@angular/common/http';

interface SelectIngredient {
  id: number;
  name: string;
  unit_of_measure: string | null;
  common: boolean;
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
// export class App {
export class App implements OnInit {
  constructor(private readonly ingredientsStore: IngredientsStore, private http: HttpClient) {}
  allIngredients: SelectIngredient[] = [];

  ngOnInit(): void {
    this.ingredientsStore.loadAll();
    this.ingredientsStore.ingredients$.subscribe(
      (items) => (this.allIngredients = items as SelectIngredient[])
    );
    this.http.get('http://localhost:8000/api/auth/csrf', { withCredentials: true }).subscribe();
  }

  readonly brand = 'PantryPilot';
  readonly googleLoginUrl = 'http://localhost:8000/auth/google/login/';
}
