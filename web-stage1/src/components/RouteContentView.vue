<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <router-view v-slot="{ Component }">
    <Transition name="route-content" mode="out-in">
      <div :key="route.path" class="route-content-shell">
        <component :is="Component" />
      </div>
    </Transition>
  </router-view>
</template>

<style scoped>
.route-content-shell {
  width: 100%;
  min-width: 0;
}

.route-content-enter-active,
.route-content-leave-active {
  transition: opacity 200ms ease, transform 200ms ease;
}

.route-content-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.route-content-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .route-content-enter-active,
  .route-content-leave-active {
    transition: none;
  }

  .route-content-enter-from {
    transform: none;
  }
}
</style>
