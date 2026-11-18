function runTwice(action) {
  action();
  action();
}
runTwice(() => console.log("Hello"));

setTimeout(() => console.log("after 1 second"), 1000);
