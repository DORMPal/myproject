import { Injectable } from '@angular/core';
import { BehaviorSubject, shareReplay } from 'rxjs';
import { ApiService } from '../services/api.service';

export interface SelectIngredient {
  id: number;
  name: string;
  unit_of_measure: string | null;
  common: boolean;
}

@Injectable({ providedIn: 'root' })
export class IngredientsStore {
  private loaded = false;

  private readonly ingredientsSubject = new BehaviorSubject<SelectIngredient[]>([]);
  readonly ingredients$ = this.ingredientsSubject.asObservable().pipe(shareReplay(1));

  constructor(private readonly api: ApiService) {}

  loadAll(): void {
    if (this.loaded) return;
    this.loaded = true;

    this.api.getAllIngredients().subscribe({
      next: (ingredients) => this.ingredientsSubject.next(ingredients as SelectIngredient[]),
      error: () => this.ingredientsSubject.next([]),
    });
  }

  // ถ้าอยากให้หน้าอื่น “ดึงค่าแบบ sync” (ไม่แนะนำเท่า observable แต่ทำได้)
  get snapshot(): SelectIngredient[] {
    return this.ingredientsSubject.value;
  }
}
