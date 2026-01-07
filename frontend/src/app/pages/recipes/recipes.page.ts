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

import { forkJoin } from 'rxjs';

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

type IntersectedIngredientGroup = {
  ingredientName: string;
  recipeIngredient: RecipeIngredientItem;
  stocks: IngredientRecord[]; // มีได้หลายอัน (เช่น นมหมดอายุวันที่ 1, นมหมดอายุวันที่ 10)
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
  userOwnedSet = new Set<string>();
  detailVisible = false;
  detailLoading = false;
  detailError: string | null = null;
  detailRecipe: RecipeDetail | null = null;
  detailSteps: string[] = []; // each step HTML/text
  userStocks: IngredientRecord[] = [];
  userStocksLoaded = false;
  userStocksLoading = false;
  userStockError: string | null = null;
  intersectingGroups: IntersectedIngredientGroup[] = [];
  intersectingIngredients: IntersectedIngredient[] = [];
  selectedIngredientIds = new Set<number>();
  bulkDeleteLoading = false;
  bulkDeleteError: string | null = null;
  bulkDeleteSuccess: string | null = null;
  selectedStockIds = new Set<number>();

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
    this.userOwnedSet.clear();
    this.detailSteps = [];
    this.selectedIngredientIds.clear();
    this.bulkDeleteError = null;
    this.bulkDeleteSuccess = null;
    this.intersectingGroups = []; // reset
    this.selectedStockIds.clear();

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

  toggleStockSelection(stockId: number, checked: boolean): void {
    if (checked) {
      this.selectedStockIds.add(stockId);
    } else {
      this.selectedStockIds.delete(stockId);
    }
  }

  removeSelectedIngredients(): void {
    if (this.selectedStockIds.size === 0) {
      this.bulkDeleteError = 'กรุณาเลือกวัตถุดิบที่ต้องการลบ';
      return;
    }

    this.bulkDeleteError = null;
    this.bulkDeleteSuccess = null;
    this.bulkDeleteLoading = true;

    const ids = Array.from(this.selectedStockIds);
    const deleteTasks = ids.map((id) => this.api.deleteUserStock(id));

    forkJoin(deleteTasks).subscribe({
      next: () => {
        this.bulkDeleteLoading = false;
        this.bulkDeleteSuccess = 'ลบวัตถุดิบออกจากสต็อกแล้ว';

        // ลบออกจาก userStocks ในเครื่อง (Local Update)
        const idSet = new Set(ids);
        this.userStocks = this.userStocks.filter((s) => !idSet.has(s.id)); // s.id คือ UserStock PK

        this.selectedStockIds.clear();
        this.updateIntersectingIngredients(); // คำนวณใหม่
      },
      error: (err) => {
        console.error(err);
        this.bulkDeleteLoading = false;
        this.bulkDeleteError = 'เกิดข้อผิดพลาดในการลบ';
      },
    });
  }

  private extractStepsFromInstructions(instructions: string | null): string[] {
    if (!instructions) return [];

    const cleanText = (str: string): string => {
      return str
        .replace(/<[^>]+>/g, '')
        .replace(/&nbsp;/g, ' ')
        .replace(/&amp;/g, '&')
        .trim();
    };

    let steps: string[] = [];
    const liMatches = instructions.match(/<li[\s\S]*?<\/li>/gi);

    if (liMatches && liMatches.length > 0) {
      steps = liMatches.map((li) => cleanText(li));
    } else {
      const blockSeparated = instructions
        .replace(/<\/(p|div|h[1-6])>/gi, '\n')
        .replace(/<br\s*\/?>/gi, '\n')
        .replace(/<\/?[^>]+(>|$)/g, '');

      // Split ด้วย Newline
      const lines = blockSeparated.split('\n');

      steps = lines
        .map((line) => cleanText(line))
        .filter((line) => {
          if (!line) return false;
          if (line.includes('อ่านบทความเพิ่มเติม')) return false;
          if (line.length < 5) return false;
          return true;
        });
    }

    return steps.map((step) => {
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

    const stockMap = new Map<string, IngredientRecord[]>();

    this.userOwnedSet.clear();
    for (const stock of this.userStocks || []) {
      const key = (stock.ingredient?.name || (stock as any).ingredient_name || '')
        .trim()
        .toLowerCase();

      if (key) {
        if (!stockMap.has(key)) {
          stockMap.set(key, []);
        }
        stockMap.get(key)?.push(stock);

        // เพิ่มลง Set ไว้ทำตัวหนังสือสีแดง (isMissing)
        this.userOwnedSet.add(key);
      }
    }

    const groups: IntersectedIngredientGroup[] = [];

    for (const ing of this.detailRecipe.ingredients || []) {
      const key = (ing.ingredient_name || '').trim().toLowerCase();
      const matchingStocks = stockMap.get(key);

      // ถ้ามีของในตู้เย็นที่ชื่อตรงกัน
      if (matchingStocks && matchingStocks.length > 0) {
        groups.push({
          ingredientName: ing.ingredient_name,
          recipeIngredient: ing,
          stocks: matchingStocks, // ส่งไปทั้ง Array (เช่น มีนม 2 ขวด)
        });
      }
    }

    // เคลียร์ selection ที่ไม่มีอยู่แล้วออก (Clean up)
    const allVisibleStockIds = new Set<number>();
    groups.forEach((g) => g.stocks.forEach((s) => allVisibleStockIds.add(s.id)));

    for (const id of Array.from(this.selectedStockIds)) {
      if (!allVisibleStockIds.has(id)) {
        this.selectedStockIds.delete(id);
      }
    }

    this.intersectingGroups = groups;
  }

  isMissing(ingredientName: string | undefined): boolean {
    if (!ingredientName) return true; // ถ้าไม่มีชื่อ ถือว่าขาดไว้ก่อน
    // ถ้ายังโหลดไม่เสร็จ ถือว่ายังไม่ขาด (จะได้ไม่แดงแวบเดียว)
    if (this.userStocksLoading) return false;

    const key = ingredientName.trim().toLowerCase();
    return !this.userOwnedSet.has(key); // ถ้าไม่มีใน Set = ขาด (return true)
  }
}
