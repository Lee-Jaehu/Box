/// <reference types="vite/client" />
declare module 'frappe-gantt' {
  export default class Gantt {
    constructor(el: string | HTMLElement | SVGElement, tasks: unknown[], options?: Record<string, unknown>);
    refresh(tasks: unknown[]): void;
    change_view_mode(mode?: string, maintainPos?: boolean): void;
    update_options(options: Record<string, unknown>): void;
  }
}
