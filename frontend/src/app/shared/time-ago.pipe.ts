import { Pipe, PipeTransform } from '@angular/core';

export function timeAgo(value: string | Date | null | undefined, now = Date.now()): string {
  if (!value) return 'nunca';
  const date = typeof value === 'string' ? new Date(withZone(value)) : value;
  const seconds = Math.max(0, Math.round((now - date.getTime()) / 1000));
  if (seconds < 5) return 'ahora';
  if (seconds < 60) return `hace ${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  return `hace ${Math.floor(hours / 24)} d`;
}

function withZone(iso: string): string {
  return /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : `${iso}Z`;
}

@Pipe({ name: 'timeAgo' })
export class TimeAgoPipe implements PipeTransform {
  transform(value: string | Date | null | undefined): string {
    return timeAgo(value);
  }
}
