import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, tap } from 'rxjs';

export interface RecipeDetail {
  id: string;
  title: string;
  description: string;
  ingredients: string[];
  steps: string[];
  [key: string]: unknown;
}

export interface IngredientRecord {
  id: string;
  name: string;
  quantity?: string;
  expires?: string;
  [key: string]: unknown;
}

export interface CurrentUser {
  id: number;
  email: string;
  name: string;
}

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  // Use absolute backend URL to ensure calls hit Django (adjust if backend host changes)
  private readonly baseUrl = 'http://localhost:8000/api';
  private readonly httpOptions = { withCredentials: true };

  constructor(private readonly http: HttpClient) {}

  getRecipeById(recipeId: string): Observable<RecipeDetail> {
    return this.http.get<RecipeDetail>(`${this.baseUrl}/recipes/${recipeId}`, this.httpOptions);
  }

  getIngredientsByUserId(userId: string): Observable<IngredientRecord[]> {
    return this.http.post<IngredientRecord[]>(`${this.baseUrl}/user`, { userId }, this.httpOptions);
  }

  addIngredientForUser(
    userId: string,
    ingredientId: string,
    payload: Record<string, unknown> = {}
  ): Observable<IngredientRecord> {
    return this.http.post<IngredientRecord>(
      `${this.baseUrl}/user/${ingredientId}`,
      { userId, ...payload },
      this.httpOptions
    );
  }

  deleteIngredientForUser(userId: string, ingredientId: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/user/${ingredientId}`, {
      body: { userId },
      ...this.httpOptions,
    });
  }

  updateIngredientForUser(
    userId: string,
    ingredientId: string,
    payload: Record<string, unknown>
  ): Observable<IngredientRecord> {
    return this.http.patch<IngredientRecord>(
      `${this.baseUrl}/user/${ingredientId}`,
      { userId, ...payload },
      this.httpOptions
    );
  }

  getAllIngredients(): Observable<IngredientRecord[]> {
    return this.http.get<IngredientRecord[]>(`${this.baseUrl}/ingredient`, this.httpOptions);
  }

  getCurrentUser(): Observable<CurrentUser> {
    return this.http.get<CurrentUser>(`${this.baseUrl}/auth/me`, this.httpOptions);
  }
}
