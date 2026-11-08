import {createApp} from 'vue'
import {createRouter,createWebHistory} from 'vue-router'
import App from './App.vue'
const router=createRouter({history:createWebHistory(),routes:[{path:'/:pathMatch(.*)*',component:()=>import('./Public.vue')},{path:'/admin/:pathMatch(.*)*',component:()=>import('./Admin.vue')}]})
createApp(App).use(router).mount('#app')
