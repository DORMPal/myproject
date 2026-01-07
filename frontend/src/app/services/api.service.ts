import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface RecipeDetail {
  id: number;
  external_id: number | null;
  title: string;
  short_detail: string | null;
  instructions: string | null;
  servings: number | null;
  level: number | null;
  created_at: string | null;
  tags: TagItem[];
  ingredients: RecipeIngredientItem[];
  thumbnail: RecipeThumbnail | null;
  [key: string]: unknown;
}

export interface TagItem {
  id: number;
  external_id: number | null;
  name: string;
  slug: string | null;
  taxonomy: string | null;
}

export interface RecipeIngredientItem {
  ingredient_name: string;
  required_quantity: string | null;
  required_unit: string | null;
  group_name: string | null;
}

export interface RecipeThumbnail {
  mime_type: string;
  data: string; // "data:image/jpeg;base64,..."
  source_url: string;
}

export interface SelectIngredient {
  id: number;
  name: string;
  unit_of_measure: string | null;
  common: boolean;
}

export interface IngredientRecord {
  id: number; // id ของ UserStock row
  ingredient: SelectIngredient;
  ingredient_id?: number; // FK ingredient (legacy)
  ingredient_name?: string; // ชื่อ ingredient (legacy)
  quantity: string | number | null; // Decimal มักถูกส่งมาเป็น string
  expiration_date: string | null; // "YYYY-MM-DD"
  date_added: string; // "YYYY-MM-DD"
  disable: boolean;
}

export interface CurrentUser {
  id: number;
  email: string;
  name: string;
}

export interface NotificationItem {
  id: number;
  user_stock: number;
  ingredient_name: string;
  ingredient_id: number;
  expiration_date: string;
  quantity: number | string | null;
  read_yet: boolean;
  created_at: string;
}

export interface NotificationResponse {
  notifications: NotificationItem[];
  unread_count: number;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface RecommendationResult extends RecipeDetail {
  missing_ingredient_count: number;
  match_percentage: number;
  missing_ingredients: string[];
  total_considered_ingredients: number;
  matched_ingredients: number;
}

export interface RecommendationResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: RecommendationResult[];
}

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private readonly baseUrl = 'http://localhost:8000/api';
  private readonly httpOptions = { withCredentials: true };

  constructor(private readonly http: HttpClient) {}

  // GET /api/recipes/?page=1&search=...&tag=...
  getRecipes(params?: {
    page?: number;
    search?: string;
    tag?: string;
  }): Observable<PaginatedResponse<RecipeDetail>> {
    let httpParams = new HttpParams();
    if (params?.page) httpParams = httpParams.set('page', String(params.page));
    if (params?.search) httpParams = httpParams.set('search', params.search);
    if (params?.tag) httpParams = httpParams.set('tag', params.tag);

    return this.http.get<PaginatedResponse<RecipeDetail>>(`${this.baseUrl}/recipes/`, {
      params: httpParams,
      ...this.httpOptions,
    });
  }

  // GET /api/recipes/<id>/
  getRecipeById(recipeId: number | string): Observable<RecipeDetail> {
    return this.http.get<RecipeDetail>(`${this.baseUrl}/recipes/${recipeId}/`, this.httpOptions);
  }

  // GET /api/recommend (top 10)
  getRecommendedRecipes(): Observable<RecommendationResponse> {
    return this.http.get<RecommendationResponse>(`${this.baseUrl}/recommend`, this.httpOptions);
  }

  getIngredientsByUserId(userId: number | string): Observable<IngredientRecord[]> {
    return this.http.post<IngredientRecord[]>(`${this.baseUrl}/user`, { userId }, this.httpOptions);
  }

  addIngredientForUser(
    userId: number | string,
    ingredientId: number | string,
    payload: Record<string, unknown> = {}
  ): Observable<IngredientRecord> {
    return this.http.post<IngredientRecord>(
      `${this.baseUrl}/user/${ingredientId}/`,
      { userId, ...payload },
      this.httpOptions
    );
  }

  deleteIngredientForUser(
    userId: number | string,
    ingredientId: number | string
  ): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/user/${ingredientId}/`, {
      body: { userId },
      ...this.httpOptions,
    });
  }

  updateIngredientForUser(
    userId: number | string,
    ingredientId: number | string,
    payload: Record<string, unknown>
  ): Observable<IngredientRecord> {
    return this.http.patch<IngredientRecord>(
      `${this.baseUrl}/user/${ingredientId}/`,
      { userId, ...payload },
      this.httpOptions
    );
  }

  getAllIngredients(): Observable<SelectIngredient[]> {
    return this.http.get<SelectIngredient[]>(`${this.baseUrl}/ingredient`, this.httpOptions);
  }

  getCurrentUser(): Observable<CurrentUser> {
    return this.http.get<CurrentUser>(`${this.baseUrl}/auth/me`, this.httpOptions);
  }

  logout(): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${this.baseUrl}/auth/logout`, {}, this.httpOptions);
  }

  getNotifications(): Observable<NotificationResponse> {
    return this.http.get<NotificationResponse>(`${this.baseUrl}/notifications`, this.httpOptions);
  }

  markNotificationAsRead(notificationId: number | string): Observable<NotificationItem> {
    return this.http.patch<NotificationItem>(
      `${this.baseUrl}/notifications/${notificationId}/`,
      {},
      this.httpOptions
    );
  }

  getTags(): Observable<TagItem[]> {
    return this.http.get<TagItem[]>(`${this.baseUrl}/tags`, this.httpOptions);
  }

  // GET /api/user
  getUserStocks(): Observable<IngredientRecord[]> {
    return this.http.get<IngredientRecord[]>(`${this.baseUrl}/user`, this.httpOptions);
  }

  // POST /api/user/<ingredient_id>/
  addUserStock(
    ingredientId: number | string,
    payload: Record<string, unknown> = {}
  ): Observable<IngredientRecord> {
    return this.http.post<IngredientRecord>(
      `${this.baseUrl}/user/${ingredientId}/`,
      payload,
      this.httpOptions
    );
  }

  // DELETE /api/user/<ingredient_id>/
  deleteUserStock(ingredientId: number | string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/user/${ingredientId}/`, this.httpOptions);
  }

  // DELETE /api/user/ingredient (bulk)
  deleteUserIngredients(ingredientIds: Array<number | string>): Observable<{ deleted: number }> {
    return this.http.delete<{ deleted: number }>(`${this.baseUrl}/user/ingredient`, {
      body: { ingredient_ids: ingredientIds },
      ...this.httpOptions,
    });
  }

  sendVoiceCommand(text: string): Observable<any> {
    // ต้องเป็น /voice-command เฉยๆ เพราะเมื่อรวมกับ baseUrl จะได้ /api/voice-command
    return this.http.post(`${this.baseUrl}/voice-command`, { text }, this.httpOptions);
  }
}
