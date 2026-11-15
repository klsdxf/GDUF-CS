import {createApp} from 'vue'
import {createRouter,createWebHistory} from 'vue-router'
import App from './App.vue'
const extra=import.meta.env.DEV?[{path:'/__design-reference',component:()=>import('./DesignReference.vue')}]:[]
const router=createRouter({history:createWebHistory(),routes:[...extra,{path:'/:pathMatch(.*)*',component:()=>import('./Public.vue')},{path:'/admin/:pathMatch(.*)*',component:()=>import('./Admin.vue')}]})
const application=createApp(App)
let adminReady=false
router.beforeEach(async(to)=>{if(to.path.startsWith('/admin')&&!adminReady){const {default:ElementPlus}=await import('element-plus');application.use(ElementPlus);adminReady=true}})
application.use(router).mount('#app')
