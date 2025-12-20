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

  responsiveOptions = [
    { breakpoint: '1199px', numVisible: 2, numScroll: 1 },
    { breakpoint: '991px', numVisible: 1, numScroll: 1 },
    { breakpoint: '575px', numVisible: 1, numScroll: 1 },
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

          // recommended = เอา 8 อันแรกไปโชว์ carousel
          this.recommended = (res.results || []).slice(0, 8);

          // รวม tags จากหน้าปัจจุบัน (เอาไว้ทำ filter แบบง่าย)
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
    // PrimeNG paginator uses "first" (index) and "rows"
    const newPage = Math.floor((event.first || 0) / (event.rows || this.pageSize)) + 1;
    this.fetchRecipes(newPage);
  }

  // รูป base64 จาก backend มาเป็น data-url แล้ว ใช้ได้เลย
  thumbSrc(recipe: RecipeDetail): string | null {
    return recipe.thumbnail?.data || null;
  }

  // ถ้าคุณยังไม่มี route detail ก็ปล่อยแค่ console ไว้ก่อน
  openRecipe(recipe: RecipeDetail): void {
    // ถ้ามีหน้า detail เช่น /page/recipes/:id ค่อยเปลี่ยนเป็น navigate ได้
    // this.router.navigate(['/page/recipes', recipe.id]);
    console.log('open recipe:', recipe.id);
  }

  trackByRecipeId(_index: number, item: RecipeDetail): number {
    return item.id;
  }

  trackByTagId(_index: number, item: TagItem): number {
    return item.id;
  }
}
