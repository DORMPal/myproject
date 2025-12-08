import { inject } from '@angular/core';
import { CanActivateFn, Router, UrlTree } from '@angular/router';

const getToken = () => localStorage.getItem('token');

/**
 * Protects authenticated pages. If no token, send user to login.
 */
export const authGuard: CanActivateFn = (): boolean | UrlTree => {
  const router = inject(Router);
  const token = getToken();
  return token ? true : router.parseUrl('/login');
};

/**
 * Redirects the app root based on auth state.
 */
export const landingGuard: CanActivateFn = (): UrlTree => {
  const router = inject(Router);
  const token = getToken();
  return token ? router.parseUrl('/page/ingredient') : router.parseUrl('/login');
};

/**
 * Prevents visiting login when already authenticated.
 */
export const loginRedirectGuard: CanActivateFn = (): boolean | UrlTree => {
  const router = inject(Router);
  const token = getToken();
  return token ? router.parseUrl('/page/ingredient') : true;
};
