<script setup lang="ts">
import SiteHeader from '../components/SiteHeader.vue'
</script>

<template>
  <SiteHeader />
  <main class="not-found">
    <p>404</p>
    <h1>页面不存在</h1>
    <RouterLink to="/">返回研究目录</RouterLink>
  </main>
</template>
