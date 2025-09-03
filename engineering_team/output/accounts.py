from datetime import datetime

class Account:
    def __init__(self, username: str, initial_deposit: float):
        """
        Initialize a new account for the user.
        
        :param username: The name of the user
        :param initial_deposit: The initial amount of money to deposit
        """
        self.username = username
        self.balance = initial_deposit
        self.holdings = {}  # Dictionary to store share holdings {symbol: quantity}
        self.transactions = []  # List to store transaction history
        self.initial_deposit = initial_deposit
        # Record the initial deposit as a transaction
        self._add_transaction("deposit", amount=initial_deposit)

    def deposit(self, amount: float) -> None:
        """
        Deposit funds to the account.
        
        :param amount: Amount to deposit
        """
        if amount <= 0:
            raise ValueError("Deposit amount must be positive.")
        self.balance += amount
        self._add_transaction("deposit", amount=amount)

    def withdraw(self, amount: float) -> None:
        """
        Withdraw funds from the account.
        
        :param amount: Amount to withdraw
        :raises ValueError: If withdrawal leads to a negative balance
        """
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive.")
        if self.balance - amount < 0:
            raise ValueError("Insufficient funds for withdrawal.")
        self.balance -= amount
        self._add_transaction("withdraw", amount=amount)

    def buy_shares(self, symbol: str, quantity: int) -> None:
        """
        Buy shares of a stock.
        
        :param symbol: The stock symbol to buy
        :param quantity: Number of shares to buy
        :raises ValueError: If insufficient funds to buy shares
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
            
        share_price = get_share_price(symbol)
        if share_price == 0.0:
            raise ValueError(f"Unknown symbol: {symbol}")
            
        total_cost = share_price * quantity
        if self.balance < total_cost:
            raise ValueError("Insufficient funds to buy shares.")
        
        self.balance -= total_cost
        self.holdings[symbol] = self.holdings.get(symbol, 0) + quantity
        self._add_transaction("buy", symbol=symbol, quantity=quantity, price=share_price)

    def sell_shares(self, symbol: str, quantity: int) -> None:
        """
        Sell shares of a stock.
        
        :param symbol: The stock symbol to sell
        :param quantity: Number of shares to sell
        :raises ValueError: If selling more shares than owned
        """
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")
            
        if symbol not in self.holdings or self.holdings[symbol] < quantity:
            raise ValueError("Not enough shares to sell.")
        
        share_price = get_share_price(symbol)
        total_revenue = share_price * quantity
        
        self.holdings[symbol] -= quantity
        if self.holdings[symbol] == 0:
            del self.holdings[symbol]
        self.balance += total_revenue
        self._add_transaction("sell", symbol=symbol, quantity=quantity, price=share_price)

    def get_portfolio_value(self) -> float:
        """
        Calculate the total value of the user's portfolio.
        
        :return: The total value of the portfolio
        """
        total_value = self.balance
        for symbol, quantity in self.holdings.items():
            total_value += get_share_price(symbol) * quantity
        return total_value

    def get_profit_loss(self) -> float:
        """
        Calculate the profit or loss from the initial deposit.
        
        :return: The profit/loss amount
        """
        return self.get_portfolio_value() - self.initial_deposit

    def get_holdings(self) -> dict:
        """
        Report the current holdings of the user.
        
        :return: A dictionary of holdings {symbol: quantity}
        """
        return self.holdings.copy()

    def get_detailed_holdings(self) -> dict:
        """
        Report the current holdings with current values.
        
        :return: A dictionary of detailed holdings information
        """
        result = {}
        for symbol, quantity in self.holdings.items():
            price = get_share_price(symbol)
            result[symbol] = {
                'quantity': quantity,
                'current_price': price,
                'total_value': quantity * price
            }
        return result

    def get_transactions(self) -> list:
        """
        List all transactions the user has made.
        
        :return: A list of transaction dictionaries
        """
        return self.transactions.copy()
    
    def _add_transaction(self, transaction_type, **kwargs):
        """
        Add a transaction to the history.
        
        :param transaction_type: Type of transaction (deposit, withdraw, buy, sell)
        :param kwargs: Additional details about the transaction
        """
        transaction = {
            'type': transaction_type,
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }
        self.transactions.append(transaction)

    def get_transaction_history_report(self) -> str:
        """
        Generate a formatted report of transaction history.
        
        :return: A formatted string report
        """
        report = f"Transaction History for {self.username}\n"
        report += "=" * 50 + "\n"
        
        for idx, transaction in enumerate(self.transactions, 1):
            t_type = transaction['type']
            timestamp = transaction['timestamp']
            
            if t_type == 'deposit':
                report += f"{idx}. [{timestamp}] Deposited ${transaction['amount']:.2f}\n"
            elif t_type == 'withdraw':
                report += f"{idx}. [{timestamp}] Withdrew ${transaction['amount']:.2f}\n"
            elif t_type == 'buy':
                symbol = transaction['symbol']
                quantity = transaction['quantity']
                price = transaction['price']
                total = quantity * price
                report += f"{idx}. [{timestamp}] Bought {quantity} shares of {symbol} at ${price:.2f} each (Total: ${total:.2f})\n"
            elif t_type == 'sell':
                symbol = transaction['symbol']
                quantity = transaction['quantity']
                price = transaction['price']
                total = quantity * price
                report += f"{idx}. [{timestamp}] Sold {quantity} shares of {symbol} at ${price:.2f} each (Total: ${total:.2f})\n"
        
        return report

    def get_portfolio_summary(self) -> str:
        """
        Generate a formatted summary of the portfolio.
        
        :return: A formatted string report
        """
        portfolio_value = self.get_portfolio_value()
        profit_loss = self.get_profit_loss()
        
        report = f"Portfolio Summary for {self.username}\n"
        report += "=" * 50 + "\n"
        report += f"Cash Balance: ${self.balance:.2f}\n"
        report += "\nHoldings:\n"
        
        if not self.holdings:
            report += "  No current holdings\n"
        else:
            for symbol, quantity in self.holdings.items():
                price = get_share_price(symbol)
                value = quantity * price
                report += f"  {symbol}: {quantity} shares at ${price:.2f} = ${value:.2f}\n"
        
        report += "\n" + "-" * 50 + "\n"
        report += f"Total Portfolio Value: ${portfolio_value:.2f}\n"
        report += f"Initial Investment: ${self.initial_deposit:.2f}\n"
        
        if profit_loss >= 0:
            report += f"Overall Profit: ${profit_loss:.2f} (+{(profit_loss/self.initial_deposit)*100:.2f}%)\n"
        else:
            report += f"Overall Loss: ${-profit_loss:.2f} ({(profit_loss/self.initial_deposit)*100:.2f}%)\n"
            
        return report

def get_share_price(symbol: str) -> float:
    """
    Fetch the current share price for the given symbol.
    
    :param symbol: The stock symbol
    :return: The current price of the stock
    """
    prices = {
        "AAPL": 150.00,
        "TSLA": 700.00,
        "GOOGL": 2800.00
    }
    return prices.get(symbol, 0.0)