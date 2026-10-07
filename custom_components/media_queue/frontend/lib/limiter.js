// Run at most n async jobs at once (thumbnail signing, so a long list does not
// send hundreds of requests to a small Home Assistant at the same time).

export function limiter(n) {
  let active = 0;
  const waiting = [];
  const next = () => {
    if (active >= n || !waiting.length) {
      return;
    }
    active += 1;
    const { job, resolve, reject } = waiting.shift();
    job()
      .then(resolve, reject)
      .finally(() => {
        active -= 1;
        next();
      });
  };
  return (job) =>
    new Promise((resolve, reject) => {
      waiting.push({ job, resolve, reject });
      next();
    });
}
