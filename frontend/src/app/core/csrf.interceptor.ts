import { Injectable } from '@angular/core';
import { HttpInterceptor, HttpRequest, HttpHandler } from '@angular/common/http';

function getCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'));
  return m ? decodeURIComponent(m[2]) : null;
}

@Injectable()
export class CsrfInterceptor implements HttpInterceptor {
  intercept(req: HttpRequest<any>, next: HttpHandler) {
    const method = req.method.toUpperCase();
    const unsafe = ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method);

    if (!unsafe) return next.handle(req);

    const token = getCookie('csrftoken');
    if (!token) return next.handle(req);

    return next.handle(
      req.clone({
        setHeaders: { 'X-CSRFToken': token },
        withCredentials: true,
      })
    );
  }
}
