"""Модуль для предобработки текста перед классификацией"""

import re
import logging
from typing import Optional

import pymorphy3
from nltk.corpus import stopwords
import nltk

# Загружаем стоп-слова при импорте
try:
    _russian_stopwords = set(stopwords.words('russian'))
except LookupError:
    nltk.download('stopwords', quiet=True)
    _russian_stopwords = set(stopwords.words('russian'))

logger = logging.getLogger(__name__)


class TextPreprocessor:
    """Класс для очистки и предобработки русских текстов"""
    
    def __init__(self):
        """Инициализация препроцессора"""
        try:
            self.morph = pymorphy3.MorphAnalyzer()
            self.russian_stopwords = _russian_stopwords
            logger.info("TextPreprocessor инициализирован успешно")
        except Exception as e:
            logger.error(f"Ошибка инициализации TextPreprocessor: {e}")
            raise
    
    def clean_text(self, text: str) -> str:
        """
        Очистка текста от спецсимволов, email, URL, цифр
        
        Args:
            text: Исходный текст
            
        Returns:
            Очищенный текст
        """
        if not text or not isinstance(text, str):
            return ""
        
        # Преобразуем в строку и делаем lowercase
        text = str(text).lower()
        
        # Удаляем email
        text = re.sub(r'\S+@\S+', ' ', text)
        
        # Удаляем URL
        text = re.sub(r'http\S+|www\S+', ' ', text)
        
        # Удаляем даты (форматы: 12.02.2025, 12/02/2025, 12-02-2025)
        text = re.sub(r'\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}', ' DATE ', text)
        
        # Заменяем числа на токен NUM
        text = re.sub(r'\d+', ' NUM ', text)
        
        # Удаляем специальные символы, оставляем только буквы, цифры и пробелы
        text = re.sub(r'[^а-яёa-z0-9\s]', ' ', text)
        
        # Удаляем множественные пробелы
        text = re.sub(r'\s+', ' ', text)
        
        return text.strip()
    
    def lemmatize(self, text: str) -> str:
        """
        Лемматизация (преобразование слов в начальную форму)
        
        Args:
            text: Очищенный текст
            
        Returns:
            Лемматизированный текст
        """
        if not text:
            return ""
        
        words = text.split()
        lemmatized_words = []
        
        for word in words:
            # Сохраняем специальные токены (NUM, DATE) без обработки
            if word in ['NUM', 'DATE']:
                lemmatized_words.append(word)
                continue
            
            # Пропускаем стоп-слова и очень короткие слова
            if word not in self.russian_stopwords and len(word) > 2:
                try:
                    # Получаем нормальную форму слова
                    parsed = self.morph.parse(word)[0]
                    lemma = parsed.normal_form
                    lemmatized_words.append(lemma)
                except Exception as e:
                    # Если не удалось обработать слово, пропускаем его
                    logger.debug(f"Не удалось обработать слово '{word}': {e}")
                    continue
        
        return ' '.join(lemmatized_words)
    
    def preprocess(self, text: str) -> str:
        """
        Полная предобработка текста: очистка + лемматизация
        
        Args:
            text: Исходный текст
            
        Returns:
            Предобработанный текст
        """
        text = self.clean_text(text)
        text = self.lemmatize(text)
        return text

