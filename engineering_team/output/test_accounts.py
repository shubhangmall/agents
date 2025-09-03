import unittest
from unittest.mock import patch
from accounts import Account

class TestAccount(unittest.TestCase):
    def setUp(self):
        # Set up a test account before each test case
        self.account = Account("test_user", 1000.0)
    
    def test_init(self):
        # Test account initialization
        self.assertEqual(self.account.user_id, "test_user")
        self.assertEqual(self.account.balance, 1000.0)
        self.assertEqual(self.account.holdings, {})
        self.assertEqual(self.account.transactions, [])
        self.assertEqual(self.account.net_deposits, 1000.0)
        
        # Test initialization with default deposit
        account_zero = Account("zero_user")
        self.assertEqual(account_zero.balance, 0.0)
        self.assertEqual(account_zero.net_deposits, 0.0)
    
    def test_deposit(self):
        # Test valid deposit
        self.account.deposit(500.0)
        self.assertEqual(self.account.balance, 1500.0)
        self.assertEqual(self.account.net_deposits, 1500.0)
        self.assertEqual(self.account.transactions[-1], ("Deposit", 500.0))
        
        # Test invalid deposit (negative amount)
        with self.assertRaises(ValueError):
            self.account.deposit(-100.0)
        
        # Test invalid deposit (zero amount)
        with self.assertRaises(ValueError):
            self.account.deposit(0.0)
    
    def test_withdraw(self):
        # Test valid withdrawal
        self.account.withdraw(300.0)
        self.assertEqual(self.account.balance, 700.0)
        self.assertEqual(self.account.net_deposits, 700.0)
        self.assertEqual(self.account.transactions[-1], ("Withdrawal", 300.0))
        
        # Test invalid withdrawal (negative amount)
        with self.assertRaises(ValueError):
            self.account.withdraw(-50.0)
        
        # Test invalid withdrawal (zero amount)
        with self.assertRaises(ValueError):
            self.account.withdraw(0.0)
        
        # Test withdrawal exceeding balance
        with self.assertRaises(ValueError):
            self.account.withdraw(800.0)
    
    @patch.object(Account, "get_share_price")
    def test_buy_shares(self, mock_get_share_price):
        # Mock the share price method
        mock_get_share_price.return_value = 50.0
        
        # Test valid purchase
        self.account.buy_shares("AAPL", 10)
        self.assertEqual(self.account.balance, 500.0)  # 1000 - (50 * 10)
        self.assertEqual(self.account.holdings, {"AAPL": 10})
        self.assertEqual(self.account.transactions[-1], ("Buy", "AAPL", 10, 50.0))
        
        # Test purchase with insufficient funds
        with self.assertRaises(ValueError):
            self.account.buy_shares("TSLA", 20)  # Would cost 1000, but only 500 available
        
        # Test invalid quantity (negative)
        with self.assertRaises(ValueError):
            self.account.buy_shares("GOOGL", -5)
        
        # Test invalid quantity (zero)
        with self.assertRaises(ValueError):
            self.account.buy_shares("GOOGL", 0)
    
    @patch.object(Account, "get_share_price")
    def test_sell_shares(self, mock_get_share_price):
        # Set up holdings first
        mock_get_share_price.return_value = 50.0
        self.account.buy_shares("AAPL", 10)  # Buy some shares to sell later
        
        # Test valid sale
        mock_get_share_price.return_value = 60.0  # Price went up
        self.account.sell_shares("AAPL", 5)
        self.assertEqual(self.account.balance, 800.0)  # 500 + (60 * 5)
        self.assertEqual(self.account.holdings, {"AAPL": 5})
        self.assertEqual(self.account.transactions[-1], ("Sell", "AAPL", 5, 60.0))
        
        # Test selling all shares (should remove the symbol from holdings)
        self.account.sell_shares("AAPL", 5)
        self.assertEqual(self.account.balance, 1100.0)  # 800 + (60 * 5)
        self.assertEqual(self.account.holdings, {})
        
        # Test selling shares user doesn't own
        with self.assertRaises(ValueError):
            self.account.sell_shares("TSLA", 5)
        
        # Test selling more shares than owned
        self.account.buy_shares("GOOGL", 3)  # Buy some shares first
        with self.assertRaises(ValueError):
            self.account.sell_shares("GOOGL", 5)  # Try to sell more than owned
        
        # Test invalid quantity (negative)
        with self.assertRaises(ValueError):
            self.account.sell_shares("GOOGL", -2)
        
        # Test invalid quantity (zero)
        with self.assertRaises(ValueError):
            self.account.sell_shares("GOOGL", 0)
    
    @patch.object(Account, "get_share_price")
    def test_get_portfolio_value(self, mock_get_share_price):
        # Set up portfolio with multiple stocks
        def side_effect(symbol):
            prices = {"AAPL": 150.0, "TSLA": 700.0, "GOOGL": 2800.0}
            return prices.get(symbol, 0.0)
        
        mock_get_share_price.side_effect = side_effect
        
        # Buy some shares
        self.account.buy_shares("AAPL", 2)  # 300 spent, 700 remaining
        self.account.buy_shares("TSLA", 1)  # 700 spent, 0 remaining
        
        # Calculate expected portfolio value
        expected_value = 0.0  # Cash balance
        expected_value += 2 * 150.0  # AAPL value
        expected_value += 1 * 700.0  # TSLA value
        
        self.assertEqual(self.account.get_portfolio_value(), expected_value)
    
    @patch.object(Account, "get_portfolio_value")
    def test_get_profit_loss(self, mock_get_portfolio_value):
        # Test profit scenario
        mock_get_portfolio_value.return_value = 1200.0
        self.assertEqual(self.account.get_profit_loss(), 200.0)  # 1200 - 1000
        
        # Test loss scenario
        mock_get_portfolio_value.return_value = 900.0
        self.assertEqual(self.account.get_profit_loss(), -100.0)  # 900 - 1000
    
    def test_get_holdings(self):
        # Test with empty holdings
        self.assertEqual(self.account.get_holdings(), {})
        
        # Test with some holdings (using the mocked buy_shares)
        with patch.object(Account, "get_share_price", return_value=50.0):
            self.account.buy_shares("AAPL", 10)
            self.account.buy_shares("TSLA", 2)
        
        expected_holdings = {"AAPL": 10, "TSLA": 2}
        self.assertEqual(self.account.get_holdings(), expected_holdings)
    
    def test_get_transactions(self):
        # Test with no transactions
        initial_transactions = self.account.get_transactions()
        self.assertEqual(initial_transactions, [])
        
        # Add some transactions
        self.account.deposit(200.0)
        with patch.object(Account, "get_share_price", return_value=50.0):
            self.account.buy_shares("AAPL", 5)
        self.account.withdraw(100.0)
        
        # Test transaction list
        transactions = self.account.get_transactions()
        self.assertEqual(len(transactions), 3)
        self.assertEqual(transactions[0], ("Deposit", 200.0))
        self.assertEqual(transactions[1], ("Buy", "AAPL", 5, 50.0))
        self.assertEqual(transactions[2], ("Withdrawal", 100.0))
    
    def test_get_share_price(self):
        # Test known symbols
        self.assertEqual(Account.get_share_price("AAPL"), 150.0)
        self.assertEqual(Account.get_share_price("TSLA"), 700.0)
        self.assertEqual(Account.get_share_price("GOOGL"), 2800.0)
        
        # Test unknown symbol
        self.assertEqual(Account.get_share_price("UNKNOWN"), 0.0)

if __name__ == "__main__":
    unittest.main()