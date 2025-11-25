import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },
  {
    path: 'login',
    loadComponent: () => import('./pages/login/login.page').then((m) => m.LoginPageComponent),
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
