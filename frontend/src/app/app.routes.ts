import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./login/login').then((m) => m.Login),
  },
  {
    path: 'cooking',
    loadComponent: () => import('./pages/cooking/cooking.page').then((m) => m.CookingPageComponent),
  },
  {
    path: 'ingredients',
    loadComponent: () =>
      import('./pages/ingredients/ingredients.page').then((m) => m.IngredientsPageComponent),
  },
  {
    path: 'recipes',
    loadComponent: () => import('./pages/recipes/recipes.page').then((m) => m.RecipesPageComponent),
  },
  { path: '**', redirectTo: 'login' },
];
