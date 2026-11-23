import type { InjectionKey } from 'vue'

export const homeIntroEntry: InjectionKey<() => boolean> = Symbol('home-intro-entry')
export const HOME_POSTER = '/redesign/assets/cs2-1-1440.webp'
export const homeIntroEnabled = import.meta.env.VITE_HOME_INTRO !== '0'
