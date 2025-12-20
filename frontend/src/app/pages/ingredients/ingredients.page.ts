import { CommonModule } from '@angular/common';
import { Component, inject, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ButtonModule } from 'primeng/button';
import { CardModule } from 'primeng/card';
import { InputTextModule } from 'primeng/inputtext';
import { TableModule } from 'primeng/table';
import { DialogModule } from 'primeng/dialog';
import { DatePickerModule } from 'primeng/datepicker';
import { SelectModule } from 'primeng/select';

import { HeaderComponent } from '../../shared/header/header.component';
import { IngredientsStore } from '../../core/ingredients.store';
import { ApiService, IngredientRecord, SelectIngredient } from '../../services/api.service';

type StockRow = {
  id: number;
  name: string;
  quantityText: string;
  expiresText: string;
};

@Component({
  selector: 'app-ingredients-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HeaderComponent,
    ButtonModule,
    CardModule,
    InputTextModule,
    TableModule,
    SelectModule,
    DialogModule,
    DatePickerModule,
  ],
  templateUrl: './ingredients.page.html',
  styleUrls: ['./ingredients.page.scss'],
})
export class IngredientsPageComponent implements OnInit {
  private readonly store = inject(IngredientsStore);
  private readonly api = inject(ApiService);

  // dropdown list (cached from store)
  ingredients$ = this.store.ingredients$;

  // dialog state
  visible = false;
  selectedIngredient?: SelectIngredient;
  date?: Date;
  quantity?: number;

  // table state (user stocks)
  searchTerm = '';
  stocks: IngredientRecord[] = [];
  loading = false;
  saving = false;
  errorMsg: string | null = null;

  ngOnInit(): void {
    // store.loadAll() ควรถูกเรียกตั้งแต่ app init แล้ว
    // แต่ถ้ายังไม่ได้เรียกที่ appConfig ก็เรียกซ้ำได้ ไม่เสียหาย
    this.store.loadAll();

    this.refreshUserStocks();
  }

  showDialog(): void {
    this.errorMsg = null;
    this.selectedIngredient = undefined;
    this.date = undefined;
    this.quantity = undefined;
    this.visible = true;
  }

  private refreshUserStocks(): void {
    this.loading = true;
    this.api.getUserStocks().subscribe({
      next: (rows) => {
        this.stocks = rows || [];
        this.loading = false;
      },
      error: (err) => {
        console.error(err);
        this.stocks = [];
        this.loading = false;
      },
    });
  }

  async onSave(): Promise<void> {
    this.errorMsg = null;

    if (!this.selectedIngredient) {
      this.errorMsg = 'กรุณาเลือกวัตถุดิบ';
      return;
    }

    this.saving = true;

    const ingredientId = this.selectedIngredient.id;

    const payload: Record<string, unknown> = {};
    if (this.date) payload['expiration_date'] = this.toYYYYMMDD(this.date);
    if (this.quantity !== undefined && this.quantity !== null && this.quantity !== ('' as any)) {
      payload['quantity'] = this.quantity;
    }

    this.api.addUserStock(ingredientId, payload).subscribe({
      next: () => {
        this.saving = false;
        this.visible = false;
        this.refreshUserStocks();
      },
      error: (err) => {
        console.error(err);
        this.saving = false;
        this.errorMsg = 'บันทึกไม่สำเร็จ (เช็คว่า login แล้วและ CORS/credentials ถูกต้อง)';
      },
    });
  }

  // ======= UI computed =======
  get totalCount(): number {
    return this.stocks.length;
  }

  // ตัวอย่าง logic (ปรับตามที่ backend ส่งจริง)
  get expiringSoon(): number {
    // นับรายการที่มีวันหมดอายุภายใน 3 วัน
    const now = new Date();
    const soon = new Date(now);
    soon.setDate(now.getDate() + 3);

    return this.stocks.filter((s) => {
      if (!s.expiration_date) return false;
      const d = new Date(s.expiration_date);
      return d >= now && d <= soon;
    }).length;
  }

  get expired(): number {
    const now = new Date();
    return this.stocks.filter((s) => {
      if (!s.expiration_date) return false;
      return new Date(s.expiration_date) < now;
    }).length;
  }

  get filteredStocks(): IngredientRecord[] {
    const term = this.searchTerm.trim().toLowerCase();
    if (!term) return this.stocks;
    return this.stocks.filter((i) => (i.ingredient_name || '').toLowerCase().includes(term));
  }

  onDelete(stock: any): void {
    // DELETE /api/user/<ingredient_id>/
    this.api.deleteUserStock(stock.ingredient.id).subscribe({
      next: () => this.refreshUserStocks(),
      error: (err) => console.error(err),
    });
  }

  // ======= helpers =======
  private toYYYYMMDD(d: Date): string {
    // ส่งให้ Django DateField แบบ "YYYY-MM-DD"
    const year = d.getFullYear();
    const month = `${d.getMonth() + 1}`.padStart(2, '0');
    const day = `${d.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  testlog(): void {
    console.log('test log');
  }
}
