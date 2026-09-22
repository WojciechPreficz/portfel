<script setup lang="ts">
defineProps<{
  error: string;
  notice: string;
}>();

defineEmits<{
  retry: [];
}>();
</script>

<template>
  <div v-if="error" class="alert alert-error">
    {{ error }}
    <button @click="$emit('retry')">Spróbuj ponownie</button>
  </div>
  <div v-if="notice" class="alert alert-notice">{{ notice }}</div>
</template>
