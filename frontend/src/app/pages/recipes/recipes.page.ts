import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface Recipe {
  title: string;
  summary: string;
  tags: string[];
  readyIn: string;
  difficulty: 'Easy' | 'Intermediate' | 'Advanced';
}

@Component({
  selector: 'app-recipes-page',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './recipes.page.html',
  styleUrls: ['./recipes.page.scss'],
})
export class RecipesPageComponent {
  search = '';
  activeFilters = new Set<string>(['All']);

  recipes: Recipe[] = [
    {
      title: 'Harissa Roasted Vegetables with Yogurt Drizzle',
      summary: 'Sheet-pan dinner with crispy chickpeas and cooling herbs.',
      tags: ['Vegetarian', 'Sheet-pan', 'Meal-prep'],
      readyIn: '30 min',
      difficulty: 'Easy',
    },
    {
      title: 'Lemon Dill Salmon with Fennel Slaw',
      summary: 'Bright, crunchy, and protein-heavy weeknight bowl.',
      tags: ['Pescatarian', 'High-protein'],
      readyIn: '25 min',
      difficulty: 'Intermediate',
    },
    {
      title: 'Gochujang Chicken Lettuce Wraps',
      summary: 'Sticky-sweet chicken with crisp lettuce and pickled radish.',
      tags: ['High-protein', 'Gluten-free'],
      readyIn: '35 min',
      difficulty: 'Intermediate',
    },
    {
      title: 'Coconut Lentil Curry',
      summary: 'Comforting, freezer-friendly curry with lime and cilantro.',
      tags: ['Vegan', 'Comfort'],
      readyIn: '40 min',
      difficulty: 'Easy',
    },
  ];

  toggleFilter(tag: string): void {
    if (tag === 'All') {
      this.activeFilters = new Set(['All']);
      return;
    }

    if (this.activeFilters.has(tag)) {
      this.activeFilters.delete(tag);
    } else {
      this.activeFilters.delete('All');
      this.activeFilters.add(tag);
    }
  }

  isActive(tag: string): boolean {
    return this.activeFilters.has(tag);
  }

  visibleRecipes(): Recipe[] {
    const query = this.search.toLowerCase().trim();
    const filters = this.activeFilters;
    return this.recipes.filter((recipe) => {
      const matchesText =
        !query ||
        recipe.title.toLowerCase().includes(query) ||
        recipe.summary.toLowerCase().includes(query);

      if (filters.has('All')) {
        return matchesText;
      }

      const matchesFilter = recipe.tags.some((tag) => filters.has(tag));
      return matchesText && matchesFilter;
    });
  }
}
