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

import { HeaderComponent } from '../../shared/header/header.component';
import { ApiService, RecipeDetail, TagItem } from '../../services/api.service';

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
  recommended: RecipeDetail[] = [];
  availableTags: TagItem[] = [];

  // modal detail state
  detailVisible = false;
  detailLoading = false;
  detailError: string | null = null;
  detailRecipe: RecipeDetail | null = null;
  detailSteps: string[] = []; // each step HTML/text

  responsiveOptions = [
    { breakpoint: '1024px', numVisible: 2, numScroll: 1 },
    { breakpoint: '768px', numVisible: 1, numScroll: 1 },
  ];

  ngOnInit(): void {
    this.fetchRecipes(1);
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

          this.recommended = (res.results || []).slice(0, 8);

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
          this.recommended = [];
          this.availableTags = [];
          this.totalCount = 0;
          this.errorMsg = 'โหลดข้อมูลไม่สำเร็จ';
          console.error(err);
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

    this.api.getRecipeById(recipe.id).subscribe({
      next: (detail) => {
        this.detailRecipe = detail;
        this.detailSteps = this.extractStepsFromInstructions(detail.instructions);
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
}
