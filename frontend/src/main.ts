import {createApp} from 'vue'
import {createRouter,createWebHistory} from 'vue-router'
import App from './App.vue'
import { homeIntroEnabled, homeIntroEntry } from './home-intro/entry'
const extra=import.meta.env.DEV?[{path:'/__design-reference',component:()=>import('./DesignReference.vue')}]:[]
const router=createRouter({history:createWebHistory(),routes:[...extra,{path:'/:pathMatch(.*)*',component:()=>import('./Public.vue')},{path:'/admin/:pathMatch(.*)*',component:()=>import('./Admin.vue')}]})
const application=createApp(App)
// Capture the document entry before Vue Router can navigate to another page.
let openingPending = homeIntroEnabled && window.location.pathname === '/'
application.provide(homeIntroEntry, () => {
  const pending = openingPending
  openingPending = false
  return pending
})
let adminReady=false
router.beforeEach(async(to)=>{if(to.path.startsWith('/admin')&&!adminReady){const {default:ElementPlus}=await import('element-plus');application.use(ElementPlus);adminReady=true}})
application.use(router).mount('#app')
