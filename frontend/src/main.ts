import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
// import { IngredientsStore } from './app/stores/ingredients.store'; // 👈 ปรับ path ให้ตรงโปรเจกต์คุณ
import { IngredientsStore } from './app/core/ingredients.store';

bootstrapApplication(App, appConfig)
  .then((appRef) => {
    const store = appRef.injector.get(IngredientsStore);
    store.loadAll(); // ✅ fetch ครั้งเดียวตอนเปิดแอป
  })
  .catch((err) => console.error(err));
