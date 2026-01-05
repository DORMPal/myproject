import { Routes } from '@angular/router';
import { authGuard, landingGuard, loginRedirectGuard } from './auth.guard';

export const routes: Routes = [
  { path: '', redirectTo: 'login', pathMatch: 'full' },

  {
    path: 'login',
    loadComponent: () => import('./login/login').then((m) => m.Login),
    canActivate: [loginRedirectGuard],
  },

  {
    path: 'page',
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'ingredient', pathMatch: 'full' },

      {
        path: 'ingredient',
        loadComponent: () =>
          import('./pages/ingredients/ingredients.page').then((m) => m.IngredientsPageComponent),
      },

      {
        path: 'recipes',
        loadComponent: () =>
          import('./pages/recipes/recipes.page').then((m) => m.RecipesPageComponent),
      },
    ],
  },

  { path: '**', redirectTo: 'login' },
];
