# src/kbot/utils/ann_model.py
import pandas as pd
import numpy as np
import tensorflow as tf
import joblib
import logging
import ta
import os

logger = logging.getLogger(__name__)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

def calculate_adaptive_trend_features(df, use_long_term=False):
    """
    Berechnet adaptive Trend-Features basierend auf logarithmischer Regression
    mit automatischer Periodenwahl durch Pearson-Korrelation.
    
    Übersetzt aus dem PineScript "Adaptive Trend Finder" von Julien_Eche.
    
    Args:
        df: DataFrame mit OHLCV-Daten und Index als Datetime
        use_long_term: Boolean, ob Long-Term (300-1200) oder Short-Term (20-200) Perioden verwendet werden
    
    Returns:
        Dictionary mit Features: pearson_r, trend_strength, detected_period, slope, std_dev, etc.
    """
    # Perioden-Arrays je nach Modus
    if use_long_term:
        periods = [300, 350, 400, 450, 500, 550, 600, 650, 700, 750, 800, 850, 900, 950, 1000, 1050, 1100, 1150, 1200]
    else:
        periods = [20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]
    
    close_prices = df['close'].values
    
    if len(close_prices) < max(periods):
        # Nicht genug Daten
        return {
            'atf_pearson_r': 0.0,
            'atf_trend_strength': 0.0,
            'atf_detected_period': 0,
            'atf_slope': 0.0,
            'atf_std_dev': 0.0,
            'atf_upper_channel_dist': 0.0,
            'atf_lower_channel_dist': 0.0
        }
    
    best_pearson_r = -1.0
    best_period = periods[0]
    best_slope = 0.0
    best_intercept = 0.0
    best_std_dev = 0.0
    
    # Für jede Periode: Log-Regression und Pearson-R berechnen
    for length in periods:
        if len(close_prices) < length:
            continue
            
        # Letzte 'length' Preise nehmen
        prices = close_prices[-length:]
        log_prices = np.log(prices)
        
        # X-Werte (Zeit-Index): 1, 2, 3, ..., length
        x_values = np.arange(1, length + 1)
        
        # Lineare Regression auf Log-Preisen
        sum_x = np.sum(x_values)
        sum_xx = np.sum(x_values * x_values)
        sum_y = np.sum(log_prices)
        sum_yx = np.sum(x_values * log_prices)
        
        # Slope und Intercept berechnen
        slope = (length * sum_yx - sum_x * sum_y) / (length * sum_xx - sum_x * sum_x)
        average = sum_y / length
        intercept = average - slope * sum_x / length + slope
        
        # Residuen und Standard-Abweichung berechnen
        regres = intercept + slope * (length - 1) * 0.5
        fitted_values = intercept + slope * (x_values - 1)
        residuals = log_prices - fitted_values
        
        # Unbiased Standard Deviation
        std_dev = np.sqrt(np.sum(residuals ** 2) / (length - 1))
        
        # Pearson-Korrelation berechnen
        dxt = log_prices - average
        dyt = fitted_values - regres
        
        sum_dxx = np.sum(dxt * dxt)
        sum_dyy = np.sum(dyt * dyt)
        sum_dyx = np.sum(dxt * dyt)
        
        divisor = sum_dxx * sum_dyy
        if divisor > 0:
            pearson_r = abs(sum_dyx / np.sqrt(divisor))  # Absolute Korrelation
        else:
            pearson_r = 0.0
        
        # Beste Korrelation speichern
        if pearson_r > best_pearson_r:
            best_pearson_r = pearson_r
            best_period = length
            best_slope = slope
            best_intercept = intercept
            best_std_dev = std_dev
    
    # Trend-Stärke klassifizieren (basierend auf Pearson-R)
    if best_pearson_r < 0.2:
        trend_strength = 0.1  # Extremely Weak
    elif best_pearson_r < 0.3:
        trend_strength = 0.2  # Very Weak
    elif best_pearson_r < 0.4:
        trend_strength = 0.3  # Weak
    elif best_pearson_r < 0.5:
        trend_strength = 0.4  # Mostly Weak
    elif best_pearson_r < 0.6:
        trend_strength = 0.5  # Somewhat Weak
    elif best_pearson_r < 0.7:
        trend_strength = 0.6  # Moderately Weak
    elif best_pearson_r < 0.8:
        trend_strength = 0.7  # Moderate
    elif best_pearson_r < 0.9:
        trend_strength = 0.8  # Moderately Strong
    elif best_pearson_r < 0.92:
        trend_strength = 0.85  # Mostly Strong
    elif best_pearson_r < 0.94:
        trend_strength = 0.9  # Strong
    elif best_pearson_r < 0.96:
        trend_strength = 0.95  # Very Strong
    elif best_pearson_r < 0.98:
        trend_strength = 0.97  # Exceptionally Strong
    else:
        trend_strength = 1.0  # Ultra Strong
    
    # Aktuellen Preis zur Trendlinie und Channels vergleichen
    current_price = close_prices[-1]
    current_log_price = np.log(current_price)
    
    # Vorhersage-Wert am aktuellen Zeitpunkt (Ende der Periode)
    predicted_log_price = best_intercept  # Am Ende (x=0 in reversed time)
    predicted_price = np.exp(predicted_log_price)
    
    # Kanal-Grenzen (2 Standardabweichungen, wie im PineScript devMultiplier=2.0)
    dev_multiplier = 2.0
    upper_bound = predicted_price * np.exp(dev_multiplier * best_std_dev)
    lower_bound = predicted_price / np.exp(dev_multiplier * best_std_dev)
    
    # Distanz zu den Kanälen (normalisiert)
    upper_channel_dist = (upper_bound - current_price) / current_price
    lower_channel_dist = (current_price - lower_bound) / current_price
    
    # Trendrichtung (positiver oder negativer Slope)
    trend_direction = 1.0 if best_slope > 0 else -1.0
    
    return {
        'atf_pearson_r': best_pearson_r,
        'atf_trend_strength': trend_strength * trend_direction,  # Mit Richtung gewichtet
        'atf_detected_period': best_period,
        'atf_slope': best_slope,
        'atf_std_dev': best_std_dev,
        'atf_upper_channel_dist': upper_channel_dist,
        'atf_lower_channel_dist': lower_channel_dist,
        'atf_price_to_trend': (current_price - predicted_price) / predicted_price  # Abweichung von der Trendlinie
    }

def create_ann_features(df):
    # Bestehende Features
    bollinger = ta.volatility.BollingerBands(close=df['close'], window=20, window_dev=2)
    df['bb_width'] = bollinger.bollinger_wband()
    df['bb_pband'] = bollinger.bollinger_pband()  # Position innerhalb der Bänder
    df['bb_hband'] = bollinger.bollinger_hband()
    df['bb_lband'] = bollinger.bollinger_lband()
    
    if 'volume' in df.columns and df['volume'].sum() > 0:
        df['obv'] = ta.volume.on_balance_volume(close=df['close'], volume=df['volume'])
        # NEU: Volume-Features
        df['volume_sma'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_sma']
        df['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume'], window=14)
        df['cmf'] = ta.volume.chaikin_money_flow(df['high'], df['low'], df['close'], df['volume'], window=20)
        df['vwap'] = ta.volume.volume_weighted_average_price(df['high'], df['low'], df['close'], df['volume'], window=14)
    else:
        df['obv'] = 0
        df['volume_sma'] = 0
        df['volume_ratio'] = 1
        df['mfi'] = 50
        df['cmf'] = 0
        df['vwap'] = df['close']
    
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)
    
    # MACD Features
    macd = ta.trend.MACD(df['close'], window_slow=26, window_fast=12, window_sign=9)
    df['macd_diff'] = macd.macd_diff()
    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    
    # ATR
    atr_indicator = ta.volatility.AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
    df['atr'] = atr_indicator.average_true_range()
    df['atr_normalized'] = (df['atr'] / df['close']) * 100

    # *** ADX WIEDER HINZUGEFÜGT (KRITISCH!) ***
    df['adx'] = ta.trend.adx(df['high'], df['low'], df['close'], window=14)
    df['adx_pos'] = ta.trend.adx_pos(df['high'], df['low'], df['close'], window=14)
    df['adx_neg'] = ta.trend.adx_neg(df['high'], df['low'], df['close'], window=14)

    # NEU: EMA Trend-Features
    df['ema20'] = ta.trend.ema_indicator(df['close'], window=20)
    df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)
    df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)
    df['price_to_ema20'] = (df['close'] - df['ema20']) / df['ema20']
    df['price_to_ema50'] = (df['close'] - df['ema50']) / df['ema50']
    
    # NEU: Momentum-Features
    df['stoch_k'] = ta.momentum.stoch(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['stoch_d'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close'], window=14, smooth_window=3)
    df['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close'], lbp=14)
    df['roc'] = ta.momentum.roc(df['close'], window=12)
    df['cci'] = ta.trend.cci(df['high'], df['low'], df['close'], window=20)
    
    # NEU: Volatilität-Features
    df['keltner_channel_hband'] = ta.volatility.keltner_channel_hband(df['high'], df['low'], df['close'], window=20)
    df['keltner_channel_lband'] = ta.volatility.keltner_channel_lband(df['high'], df['low'], df['close'], window=20)
    df['donchian_channel_hband'] = ta.volatility.donchian_channel_hband(df['high'], df['low'], df['close'], window=20)
    df['donchian_channel_lband'] = ta.volatility.donchian_channel_lband(df['high'], df['low'], df['close'], window=20)
    
    # NEU: Support/Resistance Features
    df['resistance'] = df['high'].rolling(window=20).max()
    df['support'] = df['low'].rolling(window=20).min()
    df['price_to_resistance'] = (df['resistance'] - df['close']) / df['close']
    df['price_to_support'] = (df['close'] - df['support']) / df['close']
    
    # NEU: Price Action Features
    df['high_low_range'] = (df['high'] - df['low']) / df['close']
    df['close_to_high'] = (df['high'] - df['close']) / (df['high'] - df['low'] + 0.0001)
    df['close_to_low'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.0001)
    
    # Zeitliche Features
    df['day_of_week'] = df.index.dayofweek
    df['hour_of_day'] = df.index.hour if hasattr(df.index, 'hour') else 0
    
    # Returns
    df['returns_lag1'] = df['close'].pct_change().shift(1)
    df['returns_lag2'] = df['close'].pct_change().shift(2)
    df['returns_lag3'] = df['close'].pct_change().shift(3)
    
    # NEU: Historical Volatility
    df['hist_volatility'] = df['close'].pct_change().rolling(window=20).std() * np.sqrt(252)
    
    # *** ADAPTIVE TREND FINDER FEATURES ***
    # Berechne Short-Term Trend Features
    atf_features = calculate_adaptive_trend_features(df, use_long_term=False)
    for key, value in atf_features.items():
        df[key] = value
    
    return df

def prepare_data_for_ann(df, timeframe: str, verbose: bool = True):
    """
    Definiert ein "gutes Signal" basierend auf einem dynamischen Threshold,
    der sich an der Volatilität (ATR) des jeweiligen Datensatzes orientiert.
    """
    df_with_features = create_ann_features(df.copy())
    df_with_features.dropna(inplace=True)
    if df_with_features.empty:
        return pd.DataFrame(), pd.Series()

    # Adaptive 'lookahead' und 'volatility_multiplier' je nach Zeitfenster definieren
    if 'm' in timeframe:
        lookahead = 12
        volatility_multiplier = 2.5
    elif 'h' in timeframe:
        try:
            tf_num = int(timeframe.replace('h', ''))
            if tf_num == 1:
                lookahead = 8
                volatility_multiplier = 2.0
            elif tf_num <= 4:
                lookahead = 5
                volatility_multiplier = 1.75
            else: # 6h, 12h etc.
                lookahead = 4
                volatility_multiplier = 1.75
        except ValueError:
            lookahead = 5
            volatility_multiplier = 1.75
    elif 'd' in timeframe:
        lookahead = 5
        volatility_multiplier = 1.5
    else: # Fallback
        lookahead = 5
        volatility_multiplier = 2.0

    avg_atr_pct = df_with_features['atr_normalized'].mean()
    threshold = (avg_atr_pct * volatility_multiplier) / 100

    if verbose:
        print(f"INFO: Verwende adaptive Lernziele für {timeframe}: lookahead={lookahead}, threshold={threshold*100:.2f}% (dynamisch berechnet)")

    future_returns = df_with_features['close'].pct_change(periods=lookahead).shift(-lookahead)
    df_with_features['target'] = 0
    df_with_features.loc[future_returns > threshold, 'target'] = 1
    df_with_features.loc[future_returns < -threshold, 'target'] = -1
    df_with_features = df_with_features[df_with_features['target'] != 0].copy()
    df_with_features['target'] = df_with_features['target'].replace(-1, 0)

    # *** ERWEITERTE FEATURE-LISTE MIT ALLEN NEUEN FEATURES ***
    # Feature 'ema_cross_20_50' entfernt aufgrund durchgehend niedriger Wichtigkeit (<0.2%)
    feature_cols = [
        # Basis-Features
        'bb_width', 'bb_pband', 'obv', 'rsi', 'macd_diff', 'macd', 
        'atr_normalized', 'adx', 'adx_pos', 'adx_neg',
        
        # Volume-Features
        'volume_ratio', 'mfi', 'cmf',
        
        # Trend-Features
        'price_to_ema20', 'price_to_ema50',
        
        # Momentum-Features
        'stoch_k', 'stoch_d', 'williams_r', 'roc', 'cci',
        
        # Support/Resistance
        'price_to_resistance', 'price_to_support',
        
        # Price Action
        'high_low_range', 'close_to_high', 'close_to_low',
        
        # Zeitliche Features
        'day_of_week', 'hour_of_day',
        
        # Returns & Volatilität
        'returns_lag1', 'returns_lag2', 'returns_lag3', 'hist_volatility',
        
        # *** ADAPTIVE TREND FINDER FEATURES ***
        'atf_pearson_r', 'atf_trend_strength', 'atf_slope', 
        'atf_std_dev', 'atf_upper_channel_dist', 'atf_lower_channel_dist', 
        'atf_price_to_trend'
    ]
    # ---

    X = df_with_features[feature_cols]
    y = df_with_features['target']

    return X, y

def build_and_train_model(X_train, y_train):
    """
    Verbessertes Modell mit mehr Kapazität für die erweiterten Features.
    256-128-64-32 Architektur mit Batch Normalization für bessere Stabilität.
    """
    model = tf.keras.models.Sequential([
        # Layer 1: Mehr Neuronen für komplexere Feature-Interaktionen
        tf.keras.layers.Dense(256, activation='relu', input_shape=(X_train.shape[1],)),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dropout(0.3),
        
        # Layer 2
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.Dropout(0.3),
        
        # Layer 3
        tf.keras.layers.Dense(64, activation='relu'),
        tf.keras.layers.Dropout(0.25),
        
        # Layer 4
        tf.keras.layers.Dense(32, activation='relu'),
        tf.keras.layers.Dropout(0.2),
        
        # Output
        tf.keras.layers.Dense(1, activation='sigmoid')
    ])
    
    # Verwende Adam mit reduzierter Learning Rate für bessere Konvergenz
    optimizer = tf.keras.optimizers.Adam(learning_rate=0.0005)
    model.compile(optimizer=optimizer, loss='binary_crossentropy', metrics=['accuracy'])
    
    # Callbacks: Early Stopping und Learning Rate Reduction
    early_stopping = tf.keras.callbacks.EarlyStopping(
        monitor='val_loss', 
        patience=15, 
        restore_best_weights=True,
        verbose=1
    )
    
    reduce_lr = tf.keras.callbacks.ReduceLROnPlateau(
        monitor='val_loss',
        factor=0.5,
        patience=5,
        min_lr=0.00001,
        verbose=1
    )
    
    model.fit(
        X_train, y_train, 
        validation_split=0.2, 
        epochs=150,  # Mehr Epochs mit Early Stopping
        batch_size=32, 
        callbacks=[early_stopping, reduce_lr], 
        verbose=1
    )
    
    return model

def save_model_and_scaler(model, scaler, model_path, scaler_path):
    os.makedirs(os.path.dirname(model_path), exist_ok=True)
    model.save(model_path)
    joblib.dump(scaler, scaler_path)
    logging.info(f"Modell & Scaler gespeichert.")

def load_model_and_scaler(model_path, scaler_path):
    try:
        model = tf.keras.models.load_model(model_path)
        scaler = joblib.load(scaler_path)
        logging.info(f"Modell & Scaler geladen.")
        return model, scaler
    except Exception as e:
        logging.error(f"Fehler beim Laden von Modell/Scaler: {e}")
        return None, None
