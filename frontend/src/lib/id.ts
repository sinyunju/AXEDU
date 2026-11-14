// 무작위 ID. crypto.randomUUID()는 https나 localhost에서만 동작해서,
// 휴대폰으로 http://192.168.x.x 같은 주소에 접속하면 오류가 납니다. 어디서나 되는 getRandomValues를 씁니다.
export function randomId(bytes = 16): string {
  const buf = new Uint8Array(bytes);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, '0')).join('');
}
