import { ref, onMounted, onUnmounted } from 'vue';

export function useSSE(path: string, onMessage: (event: { id: string; event: string; data: string }) => void) {
  const connected = ref(false);
  let es: EventSource | null = null;

  function connect() {
    if (es) es.close();
    const token = localStorage.getItem('yitu_token');
    const url = `/api/v1${path}${path.includes('?') ? '&' : '?'}token=${token}`;
    es = new EventSource(url);
    es.onopen = () => { connected.value = true; };
    es.onmessage = (event) => { onMessage({ id: event.lastEventId, event: event.type, data: event.data }); };
    es.addEventListener('notification', (event: MessageEvent) => {
      onMessage({ id: event.lastEventId, event: 'notification', data: event.data });
    });
    es.onerror = () => { connected.value = false; };
  }

  function disconnect() {
    if (es) { es.close(); es = null; connected.value = false; }
  }

  onMounted(connect);
  onUnmounted(disconnect);

  return { connected, reconnect: connect };
}