class Account {
  constructor(owner, balance = 0) {
    this.owner = owner;       // 'this' is JavaScript's 'self'
    this.balance = balance;
  }

  deposit(amount) {
    if (amount <= 0) throw new Error("Amount must be positive");
    this.balance += amount;
  }

  toString() {
    return `${this.owner}: ${this.balance.toFixed(2)}`;
  }
}

class SavingsAccount extends Account {
  addInterest(rate) {
    this.deposit(this.balance * rate);
  }
}

const acct = new SavingsAccount("Ada", 100);   // 'new' creates an object
acct.addInterest(0.1);
console.log(acct.toString());     // Ada: 110.00
