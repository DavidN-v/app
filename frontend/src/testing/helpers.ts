import { Role, Session } from '../app/core/models';

export function fakeJwt(expSecondsFromNow = 3600): string {
  const enc = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${enc({ alg: 'HS256' })}.${enc({ sub: 'x', exp: Math.floor(Date.now() / 1000) + expSecondsFromNow })}.sig`;
}

export function session(role: Role = 'admin', username: string = role): Session {
  return { access_token: fakeJwt(), username, role };
}
