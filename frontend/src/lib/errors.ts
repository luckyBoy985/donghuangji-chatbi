export function formatRequestError(
  message: string,
  requestId: string,
): string {
  return requestId ? `${message}（请求 ID: ${requestId}）` : message;
}
