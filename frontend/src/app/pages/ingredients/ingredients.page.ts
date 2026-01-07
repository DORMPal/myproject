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
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

import { HeaderComponent } from '../../shared/header/header.component';
import { IngredientsStore } from '../../core/ingredients.store';
import { ApiService, IngredientRecord, SelectIngredient } from '../../services/api.service';

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
    ToastModule, // ✅
  ],
  templateUrl: './ingredients.page.html',
  styleUrls: ['./ingredients.page.scss'],
})
export class IngredientsPageComponent implements OnInit {
  private readonly store = inject(IngredientsStore);
  private readonly api = inject(ApiService);
  private readonly toast = inject(MessageService); // ✅

  ingredients$ = this.store.ingredients$;

  visible = false;
  selectedIngredient?: SelectIngredient;
  date?: Date;
  quantity?: number;

  searchTerm = '';
  stocks: IngredientRecord[] = [];
  loading = false;
  saving = false;
  errorMsg: string | null = null;

  ngOnInit(): void {
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
        // console.log('rows=', rows);
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

  /** ✅ ใช้ได้ทั้ง add หรือ update (ถ้าต้องการ update ให้เรียก patch แทน post) */
  onSave(): void {
    this.errorMsg = null;

    if (!this.selectedIngredient) {
      this.errorMsg = 'กรุณาเลือกวัตถุดิบ';
      return;
    }

    this.saving = true;

    const ingredientId = this.selectedIngredient.id;

    // ✅ rule 1: ถ้าไม่เลือกวันหมดอายุ -> วันนี้ + 7 วัน
    const expDate = this.date
      ? this.stripTime(this.date)
      : this.addDays(this.stripTime(new Date()), 7);

    // ✅ rule 2: คำนวณว่าใกล้หมดอายุ/หมดอายุแล้ว และกำหนด disable
    const daysLeft = this.diffDaysFromToday(expDate); // expDate - today (เป็นวัน)
    console.log('daysLeft=', daysLeft);
    const shouldDisable = daysLeft <= 0.0000000001; // <0 expired, 0-3 near expired

    if (daysLeft <= 0) {
      this.toast.add({ severity: 'error', summary: 'หมดอายุแล้ว', detail: 'วัตถุดิบหมดอายุแล้ว' });
    } else if (daysLeft < 4) {
      this.toast.add({ severity: 'warn', summary: 'ใกล้หมดอายุ', detail: 'วัตถุดิบใกล้หมดอายุ' });
    }

    // ✅ payload ที่ส่งไป backend
    const payload: Record<string, unknown> = {
      expiration_date: this.toYYYYMMDD(expDate),
    };

    if (this.quantity !== undefined && this.quantity !== null && this.quantity !== ('' as any)) {
      payload['quantity'] = this.quantity;
    }

    // ✅ rule 3: ส่ง disable=true เฉพาะกรณีที่ต้อง disable, ถ้าไม่ส่ง = backend ควรถือว่า false
    if (shouldDisable) payload['disable'] = true;

    // ====== ADD ======
    // ถ้าคุณต้องการให้ปุ่ม Save ทำ "add" เสมอ:
    this.api.addUserStock(ingredientId, payload).subscribe({
      next: () => {
        this.saving = false;
        this.visible = false;
        this.refreshUserStocks();
      },
      error: (err) => {
        console.error(err);
        this.saving = false;
        this.errorMsg = 'บันทึกไม่สำเร็จ (เช็คว่า login แล้วและ CSRF/credentials ถูกต้อง)';
      },
    });

    // ====== UPDATE (ถ้าต้องการ) ======
    // ถ้าคุณมีโหมด edit แล้วอยากใช้ patch:
    // this.api.updateUserStock(ingredientId, payload).subscribe(...)
  }

  // ======= UI computed =======
  get totalCount(): number {
    return this.stocks.length;
  }

  get expiringSoon(): number {
    const now = this.stripTime(new Date());
    const soon = this.addDays(now, 4);
    return this.stocks.filter((s) => {
      if (!s.expiration_date) return false;
      const d = this.stripTime(new Date(s.expiration_date));
      return d > now && d <= soon;
    }).length;
  }

  get expired(): number {
    // const now = this.stripTime(new Date());
    // let b = this.stocks;

    let a = this.stocks.filter(
      (s) =>
        // if (!s.expiration_date) return false;
        // return this.stripTime(new Date(s.expiration_date)) <= now;
        // console.log(s);
        s.disable === true
    );
    // console.log(a, b, this.stocks);
    return a.length;
  }

  get filteredStocks(): IngredientRecord[] {
    const term = this.searchTerm.trim().toLowerCase();
    if (!term) return this.stocks;
    return this.stocks.filter((i) =>
      (i.ingredient?.name || i.ingredient_name || '').toLowerCase().includes(term)
    );
  }

  onDelete(stock: any): void {
    const ingredientId = stock.ingredient?.id ?? stock.ingredient_id;
    if (!ingredientId) return;

    this.api.deleteUserStock(ingredientId).subscribe({
      next: () => this.refreshUserStocks(),
      error: (err) => console.error(err),
    });
  }

  // ======= helpers =======
  private toYYYYMMDD(d: Date): string {
    const year = d.getFullYear();
    const month = `${d.getMonth() + 1}`.padStart(2, '0');
    const day = `${d.getDate()}`.padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private stripTime(d: Date): Date {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  private addDays(d: Date, days: number): Date {
    const x = new Date(d);
    x.setDate(x.getDate() + days);
    return x;
  }

  /** expDate - today เป็นจำนวนวัน (today=0) */
  private diffDaysFromToday(expDate: Date): number {
    const today = this.stripTime(new Date());
    const ms = expDate.getTime() - today.getTime();
    return Math.floor(ms / (24 * 60 * 60 * 1000));
  }
}
