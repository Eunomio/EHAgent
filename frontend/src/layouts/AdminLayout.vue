<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <div class="admin-shell">
    <header class="topbar">
      <strong>居安Agent</strong>
      <nav><a href="/">住户端</a> · 产品管理</nav>
    </header>
    <main class="page-content"><RouterView /></main>
  </div>
</template>
