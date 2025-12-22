import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { CarouselModule } from 'primeng/carousel';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { InputTextModule } from 'primeng/inputtext';
import { PaginatorModule } from 'primeng/paginator';
import { CardModule } from 'primeng/card';
import { DialogModule } from 'primeng/dialog';
import { StepperModule } from 'primeng/stepper';
import { CheckboxModule } from 'primeng/checkbox';

import { HeaderComponent } from '../../shared/header/header.component';
import {
  ApiService,
  IngredientRecord,
  RecipeDetail,
  RecipeIngredientItem,
  RecommendationResult,
  TagItem,
} from '../../services/api.service';

type IntersectedIngredient = {
  ingredientId: number;
  recipeIngredient: RecipeIngredientItem;
  stock: IngredientRecord;
};

@Component({
  selector: 'app-recipes-page',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    HeaderComponent,
    CarouselModule,
    ButtonModule,
    TagModule,
    InputTextModule,
    PaginatorModule,
    CardModule,
    DialogModule,
    StepperModule,
    CheckboxModule,
  ],
  templateUrl: './recipes.page.html',
  styleUrls: ['./recipes.page.scss'],
})
export class RecipesPageComponent implements OnInit {
  constructor(private readonly api: ApiService, private readonly router: Router) {}

  // UI state
  search = '';
  activeTag: string | null = null;

  // paging (DRF page size = 20)
  page = 1;
  pageSize = 20;
  totalCount = 0;
  loading = false;
  errorMsg: string | null = null;

  // data
  results: RecipeDetail[] = [];
  recommended: RecommendationResult[] = [];
  availableTags: TagItem[] = [];

  // modal detail state
  detailVisible = false;
  detailLoading = false;
  detailError: string | null = null;
  detailRecipe: RecipeDetail | null = null;
  detailSteps: string[] = []; // each step HTML/text
  userStocks: IngredientRecord[] = [];
  userStocksLoaded = false;
  userStocksLoading = false;
  userStockError: string | null = null;
  intersectingIngredients: IntersectedIngredient[] = [];
  selectedIngredientIds = new Set<number>();
  bulkDeleteLoading = false;
  bulkDeleteError: string | null = null;
  bulkDeleteSuccess: string | null = null;

  responsiveOptions = [
    { breakpoint: '1024px', numVisible: 2, numScroll: 1 },
    { breakpoint: '768px', numVisible: 1, numScroll: 1 },
  ];

  ngOnInit(): void {
    this.fetchRecipes(1);
    this.fetchRecommended();
  }

  fetchRecipes(page: number): void {
    this.loading = true;
    this.errorMsg = null;

    this.api
      .getRecipes({
        page,
        search: this.search?.trim() || undefined,
        tag: this.activeTag || undefined,
      })
      .subscribe({
        next: (res) => {
          this.page = page;
          this.totalCount = res.count;
          this.results = res.results;

          const map = new Map<number, TagItem>();
          for (const r of res.results || []) {
            for (const t of r.tags || []) {
              if (!map.has(t.id)) map.set(t.id, t);
            }
          }
          this.availableTags = Array.from(map.values()).sort((a, b) =>
            (a.name || '').localeCompare(b.name || '')
          );

          this.loading = false;
        },
        error: (err) => {
          this.loading = false;
          this.results = [];
          this.availableTags = [];
          this.totalCount = 0;
          this.errorMsg = 'โหลดข้อมูลไม่สำเร็จ';
          console.error(err);
        },
      });
  }

  private fetchRecommended(): void {
    this.api.getRecommendedRecipes().subscribe({
      next: (res) => {
        this.recommended = res.results || [];
      },
      error: (err) => {
        console.error(err);
        this.recommended = [];
      },
    });
  }

  onSearch(): void {
    this.fetchRecipes(1);
  }

  clearSearch(): void {
    this.search = '';
    this.fetchRecipes(1);
  }

  setTag(tagName: string | null): void {
    this.activeTag = tagName;
    this.fetchRecipes(1);
  }

  onPageChange(event: any): void {
    const newPage = Math.floor((event.first || 0) / (event.rows || this.pageSize)) + 1;
    this.fetchRecipes(newPage);
  }

  thumbSrc(recipe: RecipeDetail): string | null {
    return recipe.thumbnail?.data || null;
  }

  /** ✅ click "ดูเมนู" -> fetch detail -> show dialog */
  openRecipe(recipe: RecipeDetail): void {
    this.detailVisible = true;
    this.detailLoading = true;
    this.detailError = null;
    this.detailRecipe = null;
    this.detailSteps = [];
    this.selectedIngredientIds.clear();
    this.bulkDeleteError = null;
    this.bulkDeleteSuccess = null;

    this.loadUserStocksIfNeeded();
    this.api.getRecipeById(recipe.id).subscribe({
      next: (detail) => {
        this.detailRecipe = detail;
        this.detailSteps = this.extractStepsFromInstructions(detail.instructions);
        this.updateIntersectingIngredients();
        this.detailLoading = false;
      },
      error: (err) => {
        this.detailLoading = false;
        this.detailError = 'โหลดรายละเอียดเมนูไม่สำเร็จ';
        console.error(err);
      },
    });
  }

  onCloseDetail(): void {
    // optional reset
    // this.detailRecipe = null;
    // this.detailSteps = [];
    // this.detailError = null;
  }

  trackByRecipeId(_index: number, item: RecipeDetail): number {
    return item.id;
  }

  trackByTagId(_index: number, item: TagItem): number {
    return item.id;
  }

  toggleIngredientSelection(ingredientId: number, checked: boolean): void {
    if (checked) {
      this.selectedIngredientIds.add(ingredientId);
    } else {
      this.selectedIngredientIds.delete(ingredientId);
    }
  }

  removeSelectedIngredients(): void {
    if (this.selectedIngredientIds.size === 0) {
      this.bulkDeleteError = 'กรุณาเลือกวัตถุดิบที่ต้องการลบ';
      return;
    }

    this.bulkDeleteError = null;
    this.bulkDeleteSuccess = null;
    this.bulkDeleteLoading = true;

    const ids = Array.from(this.selectedIngredientIds);
    this.api.deleteUserIngredients(ids).subscribe({
      next: (res) => {
        this.bulkDeleteLoading = false;
        this.bulkDeleteSuccess = 'ลบวัตถุดิบออกจากสต็อกแล้ว';
        // remove local stocks that were deleted
        const idSet = new Set(ids);
        this.userStocks = this.userStocks.filter(
          (s) => !idSet.has(this.ingredientIdFromStock(s) ?? -1)
        );
        this.selectedIngredientIds.clear();
        this.updateIntersectingIngredients();
      },
      error: (err) => {
        console.error(err);
        this.bulkDeleteLoading = false;
        this.bulkDeleteError = 'ลบวัตถุดิบไม่สำเร็จ (ตรวจสอบการเข้าสู่ระบบ)';
      },
    });
  }

  /** ✅ Parse <ol><li>..</li></ol> -> [step1, step2, ...] (HTML-safe-ish) */
  private extractStepsFromInstructions(instructions: string | null): string[] {
    if (!instructions) return [];

    // normalize
    const html = instructions.replace(/\r?\n/g, ' ');

    // grab li blocks (keeps inner html)
    const liMatches = html.match(/<li\b[^>]*>[\s\S]*?<\/li>/gi);
    if (liMatches && liMatches.length) {
      return liMatches.map((li) => {
        // remove the outer <li> tags but keep inner formatting
        return li
          .replace(/^<li\b[^>]*>/i, '')
          .replace(/<\/li>$/i, '')
          .trim();
      });
    }

    // fallback: strip tags + split by period-ish (very rough)
    const text = html
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    if (!text) return [];
    return text
      .split(' . ')
      .map((s) => s.trim())
      .filter(Boolean);
  }

  private loadUserStocksIfNeeded(): void {
    if (this.userStocksLoaded || this.userStocksLoading) {
      this.updateIntersectingIngredients();
      return;
    }

    this.userStocksLoading = true;
    this.userStockError = null;
    this.api.getUserStocks().subscribe({
      next: (rows) => {
        this.userStocks = rows || [];
        this.userStocksLoaded = true;
        this.userStocksLoading = false;
        this.updateIntersectingIngredients();
      },
      error: (err) => {
        console.error(err);
        this.userStocks = [];
        this.userStocksLoaded = false;
        this.userStocksLoading = false;
        this.userStockError = 'โหลดวัตถุดิบของคุณไม่สำเร็จ (ต้องเข้าสู่ระบบ)';
        this.updateIntersectingIngredients();
      },
    });
  }

  private ingredientIdFromStock(stock: IngredientRecord): number | null {
    const id = (stock.ingredient as any)?.id ?? (stock as any).ingredient_id;
    return typeof id === 'number' ? id : null;
  }

  private updateIntersectingIngredients(): void {
    if (!this.detailRecipe) {
      this.intersectingIngredients = [];
      return;
    }

    const stockMap = new Map<string, IngredientRecord>();
    for (const stock of this.userStocks || []) {
      const key = (stock.ingredient?.name || (stock as any).ingredient_name || '')
        .trim()
        .toLowerCase();
      if (key) stockMap.set(key, stock);
    }

    const list: IntersectedIngredient[] = [];
    const seen = new Set<number>();
    for (const ing of this.detailRecipe.ingredients || []) {
      const key = (ing.ingredient_name || '').trim().toLowerCase();
      const stock = stockMap.get(key);
      if (!stock) continue;
      const ingredientId = this.ingredientIdFromStock(stock);
      if (ingredientId === null || seen.has(ingredientId)) continue;

      seen.add(ingredientId);
      list.push({
        ingredientId,
        recipeIngredient: ing,
        stock,
      });
    }

    // remove selections that are no longer visible
    for (const id of Array.from(this.selectedIngredientIds)) {
      if (!seen.has(id)) this.selectedIngredientIds.delete(id);
    }

    this.intersectingIngredients = list;
  }
}
