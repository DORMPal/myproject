import { CommonModule } from '@angular/common';
import { Component, computed, signal } from '@angular/core';

interface Dish {
  name: string;
  time: string;
  skill: 'Easy' | 'Intermediate' | 'Advanced';
  tags: string[];
  missing: string[];
  canCook: boolean;
}

@Component({
  selector: 'app-cooking-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './cooking.page.html',
  styleUrls: ['./cooking.page.scss'],
})
export class CookingPageComponent {
  private dishes = signal<Dish[]>([
    {
      name: 'Creamy Pesto Gnocchi',
      time: '22 min',
      skill: 'Easy',
      tags: ['Vegetarian', 'Quick'],
      missing: [],
      canCook: true,
    },
    {
      name: 'Miso-Glazed Salmon Bowl',
      time: '28 min',
      skill: 'Intermediate',
      tags: ['Pescatarian', 'High-protein'],
      missing: ['sesame seeds'],
      canCook: true,
    },
    {
      name: 'Spicy Chickpea Wraps',
      time: '18 min',
      skill: 'Easy',
      tags: ['Vegan', 'Meal-prep'],
      missing: [],
      canCook: true,
    },
    {
      name: 'Slow Baked Ribs',
      time: '2h 10m',
      skill: 'Advanced',
      tags: ['Comfort', 'Weekend'],
      missing: ['smoked paprika', 'thyme'],
      canCook: false,
    },
  ]);

  activeFilter = signal<'all' | 'quick' | 'vegetarian' | 'protein'>('all');

  filteredDishes = computed(() => {
    const filter = this.activeFilter();
    return this.dishes().filter((dish) => {
      if (filter === 'quick') {
        return dish.time.includes('min');
      }
      if (filter === 'vegetarian') {
        return dish.tags.includes('Vegetarian') || dish.tags.includes('Vegan');
      }
      if (filter === 'protein') {
        return dish.tags.includes('High-protein');
      }
      return true;
    });
  });

  setFilter(filter: 'all' | 'quick' | 'vegetarian' | 'protein'): void {
    this.activeFilter.set(filter);
  }
}
