import { computed, ref } from 'vue';
import { ApiError, getAuthStatus, login as loginRequest, logout as logoutRequest } from '../api';

export const useAuth = () => {
  const authStatus = ref<'checking' | 'authenticated' | 'unauthenticated'>('checking');
  const isAuthenticated = computed(() => authStatus.value === 'authenticated');
  const authMessage = ref('');
  const loginSubmitting = ref(false);

  const expireSession = () => {
    authStatus.value = 'unauthenticated';
    authMessage.value = 'Sesja wygasła';
    loginSubmitting.value = false;
  };

  const checkSession = async () => {
    try {
      const session = await getAuthStatus();
      authStatus.value = session.authenticated ? 'authenticated' : 'unauthenticated';
    } catch (reason) {
      authStatus.value = 'unauthenticated';
      authMessage.value =
        reason instanceof ApiError && reason.status === 401
          ? ''
          : reason instanceof Error
            ? reason.message
            : 'Nie udało się sprawdzić sesji.';
    }
  };

  const login = async (password: string, onAuthenticated: () => Promise<void>) => {
    loginSubmitting.value = true;
    authMessage.value = '';
    try {
      await loginRequest(password);
      authStatus.value = 'authenticated';
      await onAuthenticated();
    } catch (reason) {
      authMessage.value =
        reason instanceof ApiError && reason.status === 401
          ? 'Nieprawidłowe hasło.'
          : reason instanceof Error
            ? reason.message
            : 'Nie udało się zalogować.';
    } finally {
      loginSubmitting.value = false;
    }
  };

  const logout = async () => {
    await logoutRequest();
    authMessage.value = '';
    authStatus.value = 'unauthenticated';
  };

  return {
    authStatus,
    isAuthenticated,
    authMessage,
    loginSubmitting,
    expireSession,
    checkSession,
    login,
    logout,
  };
};
