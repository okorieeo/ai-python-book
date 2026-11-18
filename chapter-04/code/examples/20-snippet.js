function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

wait(500)
  .then(() => console.log("done waiting"))
  .catch((error) => console.log("failed", error))
  .finally(() => console.log("always runs"));
