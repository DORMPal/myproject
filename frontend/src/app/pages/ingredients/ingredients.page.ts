import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';

interface Ingredient {
  name: string;
  quantity: string;
  expires: string;
  status: 'fresh' | 'warning' | 'urgent';
  notes?: string;
}

@Component({
  selector: 'app-ingredients-page',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './ingredients.page.html',
  styleUrls: ['./ingredients.page.scss'],
})
export class IngredientsPageComponent {
  ingredients: Ingredient[] = [
    { name: 'Milk', quantity: '1L', expires: 'Tomorrow', status: 'urgent', notes: 'Open' },
    { name: 'Milk', quantity: '500ml', expires: 'Apr 8', status: 'warning' },
    { name: 'Baby spinach', quantity: '120g', expires: 'Apr 6', status: 'warning' },
    { name: 'Parmesan', quantity: '1/2 wedge', expires: 'Apr 20', status: 'fresh' },
    { name: 'Chicken thighs', quantity: '4 pcs', expires: 'Apr 5', status: 'urgent', notes: 'Marinated' },
    { name: 'Chickpeas', quantity: '2 cans', expires: 'Aug 12', status: 'fresh' },
    { name: 'Fresh basil', quantity: '1 bunch', expires: 'Apr 4', status: 'urgent' },
    { name: 'Gnocchi', quantity: '2 packs', expires: 'May 2', status: 'fresh' },
  ];
}
