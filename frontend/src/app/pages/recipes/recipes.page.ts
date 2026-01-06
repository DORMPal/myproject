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
import { IconFieldModule } from 'primeng/iconfield';
import { InputIconModule } from 'primeng/inputicon';
import { SelectModule } from 'primeng/select';
import { SkeletonModule } from 'primeng/skeleton';

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
    IconFieldModule,
    InputIconModule,
    SelectModule,
    SkeletonModule,
  ],
  templateUrl: './recipes.page.html',
  styleUrls: ['./recipes.page.scss'],
})
export class RecipesPageComponent implements OnInit {
  constructor(private readonly api: ApiService, private readonly router: Router) {}

  // UI state
  search = '';
  activeTag: string | null = null;
  tagSearch = '';
  filteredTags: TagItem[] = [];
  allTagsOptions: any[] = [];

  // paging (DRF page size = 20)
  page = 1;
  pageSize = 20;
  totalCount = 0;
  loading = false;
  loadingRecommended = false;
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
    this.fetchTags();
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

          this.loading = false;
        },
        error: (err) => {
          this.loading = false;
          this.results = [];
          // this.availableTags = [];
          this.totalCount = 0;
          this.errorMsg = 'โหลดข้อมูลไม่สำเร็จ';
          console.error(err);
        },
      });
  }

  private fetchRecommended(): void {
    this.loadingRecommended = true;
    this.api.getRecommendedRecipes().subscribe({
      next: (res) => {
        this.recommended = res.results || [];
        this.loadingRecommended = false;
      },
      error: (err) => {
        console.error(err);
        this.recommended = [];
        this.loadingRecommended = false;
      },
    });
  }

  private fetchTags(): void {
    this.api.getTags().subscribe({
      next: (tags) => {
        this.availableTags = tags || [];
        this.filteredTags = this.availableTags;
        this.allTagsOptions = [...this.availableTags];
      },
      error: (err) => {
        console.error(err);
        this.availableTags = [];
        this.filteredTags = [];
        this.allTagsOptions = [{ name: 'All Tags', value: null }];
      },
    });
  }

  filterTags(): void {
    if (!this.tagSearch.trim()) {
      this.filteredTags = this.availableTags;
    } else {
      const searchTerm = this.tagSearch.toLowerCase();
      this.filteredTags = this.availableTags.filter((tag) =>
        tag.name.toLowerCase().includes(searchTerm)
      );
    }
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

  trackBySkeletonId(_index: number, item: number): number {
    return item;
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

    // 1. Helper function: ลบ HTML Tags และ Decode Entities พื้นฐาน
    const cleanText = (str: string): string => {
      return str
        .replace(/<[^>]+>/g, '') // ลบ HTML Tags
        .replace(/&nbsp;/g, ' ') // เปลี่ยน &nbsp; เป็น space
        .replace(/&amp;/g, '&') // เปลี่ยน &amp; เป็น &
        .trim();
    };

    let steps: string[] = [];

    // ---------------------------------------------------------
    // Strategy 1: ถ้ามี <li> ให้ใช้ <li> (แม่นยำที่สุด)
    // ---------------------------------------------------------
    const liMatches = instructions.match(/<li[\s\S]*?<\/li>/gi);

    if (liMatches && liMatches.length > 0) {
      steps = liMatches.map((li) => cleanText(li));
    }
    // ---------------------------------------------------------
    // Strategy 2: ถ้าไม่มี <li> ให้แบ่งตาม Block Elements (<p>, <br>, <div>)
    // ---------------------------------------------------------
    else {
      // แปลงจุดจบของ Block Elements ให้เป็นตัวอักษรพิเศษ (เช่น Newline) เพื่อใช้ split
      const blockSeparated = instructions
        .replace(/<\/(p|div|h[1-6])>/gi, '\n') // จบ paragraph ให้ขึ้นบรรทัดใหม่
        .replace(/<br\s*\/?>/gi, '\n') // เจอ <br> ให้ขึ้นบรรทัดใหม่
        .replace(/<\/?[^>]+(>|$)/g, ''); // ลบ tag อื่นๆ ที่เหลือออก

      // Split ด้วย Newline
      const lines = blockSeparated.split('\n');

      steps = lines
        .map((line) => cleanText(line))
        .filter((line) => {
          // Filter กรองข้อมูลขยะ
          if (!line) return false; // ไม่เอาบรรทัดว่าง
          if (line.includes('อ่านบทความเพิ่มเติม')) return false; // ตัดลิงก์ท้ายบทความ (เคสที่ 3)
          if (line.length < 5) return false; // ตัดบรรทัดที่สั้นเกินไป (อาจจะเป็นเลขหน้า หรือเศษขยะ)
          return true;
        });
    }

    // ---------------------------------------------------------
    // Final Cleanup: ลบตัวเลขนำหน้า (เช่น "1. ", "2. ")
    // เพื่อให้ Frontend ไปใส่เลขเอง หรือแสดงผลได้สวยงามไม่ซ้ำซ้อน
    // ---------------------------------------------------------
    return steps.map((step) => {
      // Regex: ค้นหาตัวเลขต้นประโยค ตามด้วยจุด และเว้นวรรค (เช่น "1. ล้าง..." หรือ "2.ใส่...")
      return step.replace(/^\d+\.?\s*/, '');
    });
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
