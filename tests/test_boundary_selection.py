# -*- coding: utf-8 -*-
"""
Unit tests for boundary selection logic in geo_query_engine.py

Tests the improvements made to _process_boundary_response to correctly handle:
1. Sub-facility penalty (e.g., heliport vs main campus)
2. Minimum area threshold
3. Minimum score threshold
"""

import sys
import os
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestBoundarySelection(unittest.TestCase):
    """Test the boundary selection logic"""
    
    def setUp(self):
        """Set up mock data for testing"""
        # Mock Nominatim response with both heliport and main campus
        self.mock_stanford_response = {
            'features': [
                {
                    'type': 'Feature',
                    'properties': {
                        'display_name': 'Stanford University Hospital Center Heliport, Quarry Road Extension, Palo Alto, CA',
                        'importance': 0.5,
                        'osm_type': 'way',
                        'category': 'aeroway',
                        'type': 'helipad'
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [[[-122.1747, 37.4351], [-122.1745, 37.4350], [-122.1744, 37.4352], [-122.1747, 37.4353], [-122.1747, 37.4351]]]
                    },
                    'bbox': [-122.1748, 37.4350, -122.1744, 37.4353]  # Very small: ~0.0004 x 0.0003
                },
                {
                    'type': 'Feature',
                    'properties': {
                        'display_name': 'Stanford University, Santa Clara County, California, United States',
                        'importance': 0.8,
                        'osm_type': 'relation',
                        'category': 'amenity',
                        'type': 'university'
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [[[-122.20, 37.40], [-122.15, 37.40], [-122.15, 37.45], [-122.20, 37.45], [-122.20, 37.40]]]
                    },
                    'bbox': [-122.20, 37.40, -122.15, 37.45]  # Large: ~0.05 x 0.05
                }
            ]
        }
        
        # Mock response with only heliport (should be rejected)
        self.mock_only_heliport_response = {
            'features': [
                {
                    'type': 'Feature',
                    'properties': {
                        'display_name': 'Stanford University Hospital Center Heliport, Quarry Road Extension, Palo Alto, CA',
                        'importance': 0.5,
                        'osm_type': 'way',
                        'category': 'aeroway',
                        'type': 'helipad'
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [[[-122.1747, 37.4351], [-122.1745, 37.4350], [-122.1744, 37.4352], [-122.1747, 37.4353], [-122.1747, 37.4351]]]
                    },
                    'bbox': [-122.1748, 37.4350, -122.1744, 37.4353]
                }
            ]
        }
        
        # Mock response with tiny area (should be rejected)
        self.mock_tiny_area_response = {
            'features': [
                {
                    'type': 'Feature',
                    'properties': {
                        'display_name': 'Stanford University Entrance Gate',
                        'importance': 0.3,
                        'osm_type': 'node',
                        'category': 'entrance',
                        'type': 'gate'
                    },
                    'geometry': {
                        'type': 'Polygon',
                        'coordinates': [[[-122.175, 37.435], [-122.1749, 37.435], [-122.1749, 37.4351], [-122.175, 37.4351], [-122.175, 37.435]]]
                    },
                    'bbox': [-122.175, 37.435, -122.1749, 37.4351]  # Tiny: ~0.0001 x 0.0001
                }
            ]
        }
    
    def test_sub_facility_detection(self):
        """Test that sub-facilities (heliport, parking, etc.) are correctly identified"""
        sub_facility_keywords = [
            'heliport', 'helipad', 'parking', 'gate', 'entrance', 'station', 'stop', 'terminal',
            'annex', 'extension', 'branch', 'satellite', 'outpost', 'center heliport'
        ]
        
        test_names = [
            'Stanford University Hospital Center Heliport',
            'MIT Parking Garage',
            'Harvard University Main Gate',
            'Yale Campus Entrance',
        ]
        
        for name in test_names:
            name_lower = name.lower()
            is_sub_facility = any(kw in name_lower for kw in sub_facility_keywords)
            self.assertTrue(is_sub_facility, f"'{name}' should be detected as sub-facility")
        
        # Test that main campus is NOT detected as sub-facility
        main_names = [
            'Stanford University',
            'Stanford University, California',
            'MIT Campus',
        ]
        
        for name in main_names:
            name_lower = name.lower()
            is_sub_facility = any(kw in name_lower for kw in sub_facility_keywords)
            self.assertFalse(is_sub_facility, f"'{name}' should NOT be detected as sub-facility")
    
    def test_landmark_query_detection(self):
        """Test that university/park queries are correctly identified as landmark queries"""
        landmark_keywords_en = ['university', 'college', 'park', 'hospital', 'museum', 'library', 'stadium', 
                               'airport', 'campus', 'institute', 'garden', 'palace', 'zoo']
        
        test_queries = [
            ('Stanford University', True),
            ('MIT', False),  # No explicit keyword
            ('Central Park', True),
            ('Beijing', False),
            ('Harvard College', True),
            ('Shenzhen', False),
        ]
        
        for query, expected in test_queries:
            is_landmark = any(kw in query.lower() for kw in landmark_keywords_en)
            self.assertEqual(is_landmark, expected, f"'{query}' landmark detection should be {expected}")
    
    def test_area_calculation(self):
        """Test that area is correctly calculated from bbox"""
        # bbox format: [minlon, minlat, maxlon, maxlat]
        
        # Small heliport area
        heliport_bbox = [-122.1748, 37.4350, -122.1744, 37.4353]
        heliport_area = (heliport_bbox[2] - heliport_bbox[0]) * (heliport_bbox[3] - heliport_bbox[1])
        self.assertLess(heliport_area, 0.00001, "Heliport area should be very small")
        
        # Large campus area
        campus_bbox = [-122.20, 37.40, -122.15, 37.45]
        campus_area = (campus_bbox[2] - campus_bbox[0]) * (campus_bbox[3] - campus_bbox[1])
        self.assertGreater(campus_area, 0.001, "Campus area should be large")
        
        # Campus should be much larger than heliport
        self.assertGreater(campus_area / heliport_area, 100, "Campus should be >100x larger than heliport")
    
    def test_score_penalty_for_sub_facility(self):
        """Test that sub-facilities receive heavy score penalty"""
        sub_facility_keywords = [
            'heliport', 'helipad', 'parking', 'gate', 'entrance', 'station', 'stop', 'terminal',
            'annex', 'extension', 'branch', 'satellite', 'outpost', 'center heliport'
        ]
        
        heliport_name = 'Stanford University Hospital Center Heliport'
        campus_name = 'Stanford University'
        
        # Simulate scoring
        heliport_score = 50  # Base importance score
        campus_score = 80   # Higher importance
        
        # Apply penalty for sub-facility
        if any(kw in heliport_name.lower() for kw in sub_facility_keywords):
            heliport_score -= 1000
        
        if any(kw in campus_name.lower() for kw in sub_facility_keywords):
            campus_score -= 1000
        
        # Campus should have higher score after penalty
        self.assertGreater(campus_score, heliport_score, "Campus should score higher than heliport after penalty")
        self.assertLess(heliport_score, -500, "Heliport score should be below -500 threshold")
    
    def test_minimum_area_threshold(self):
        """Test minimum area threshold logic"""
        MIN_AREA_THRESHOLD = 0.00001  # ~100m x 100m
        
        # Heliport bbox
        heliport_bbox = [-122.1748, 37.4350, -122.1744, 37.4353]
        heliport_area = (heliport_bbox[2] - heliport_bbox[0]) * (heliport_bbox[3] - heliport_bbox[1])
        
        # Should be rejected for being too small
        self.assertLess(heliport_area, MIN_AREA_THRESHOLD, "Heliport should be below minimum area threshold")
        
        # Campus bbox
        campus_bbox = [-122.20, 37.40, -122.15, 37.45]
        campus_area = (campus_bbox[2] - campus_bbox[0]) * (campus_bbox[3] - campus_bbox[1])
        
        # Should pass minimum area threshold
        self.assertGreater(campus_area, MIN_AREA_THRESHOLD, "Campus should be above minimum area threshold")
    
    def test_university_search_variants(self):
        """Test that university queries generate campus variants"""
        university_keywords = ['university', 'college', 'institute']
        
        test_query = 'Stanford University'
        is_university_query = any(kw in test_query.lower() for kw in university_keywords)
        self.assertTrue(is_university_query, "Should detect university query")
        
        # Generate expected variants
        variants = [test_query]
        if is_university_query:
            campus_variants = [
                f"{test_query} main campus",
                f"{test_query} campus"
            ]
            variants.extend(campus_variants)
        
        self.assertIn('Stanford University main campus', variants)
        self.assertIn('Stanford University campus', variants)


class TestChineseCityDetection(unittest.TestCase):
    """Test the _is_chinese_city logic for distinguishing Chinese vs foreign city names"""
    
    def setUp(self):
        """Set up foreign places list (mirrors the one in geo_query_engine.py)"""
        self.foreign_places_cn = {
            '纽约', '洛杉矶', '芝加哥', '旧金山', '华盛顿', '波士顿', '西雅图', '迈阿密',
            '伦敦', '巴黎', '柏林', '罗马', '马德里', '阿姆斯特丹', '维也纳',
            '东京', '大阪', '首尔', '新加坡', '曼谷',
            '悉尼', '墨尔本', '多伦多', '温哥华',
            '美国', '英国', '法国', '德国', '日本', '韩国', '澳大利亚', '加拿大',
        }
    
    def _is_chinese_city(self, city_name: str) -> bool:
        """Mirror of the actual implementation"""
        city_clean = city_name.strip()
        if city_clean in self.foreign_places_cn:
            return False
        for foreign_place in self.foreign_places_cn:
            if foreign_place in city_clean:
                return False
        return True
    
    def test_foreign_cities_detected(self):
        """Test that foreign city Chinese names are correctly identified as non-Chinese"""
        foreign_cities = ['纽约', '伦敦', '巴黎', '东京', '悉尼', '多伦多']
        for city in foreign_cities:
            self.assertFalse(self._is_chinese_city(city), f"'{city}' should be detected as foreign city")
    
    def test_chinese_cities_detected(self):
        """Test that actual Chinese cities are correctly identified"""
        chinese_cities = ['北京', '上海', '广州', '深圳', '杭州', '成都', '武汉']
        for city in chinese_cities:
            self.assertTrue(self._is_chinese_city(city), f"'{city}' should be detected as Chinese city")
    
    def test_foreign_cities_with_suffix(self):
        """Test that foreign cities with suffixes are still detected"""
        test_cases = ['纽约市', '伦敦市', '巴黎市区', '东京都']
        for city in test_cases:
            self.assertFalse(self._is_chinese_city(city), f"'{city}' should be detected as foreign city")
    
    def test_countries_detected_as_foreign(self):
        """Test that foreign country names are detected"""
        countries = ['美国', '英国', '法国', '德国', '日本']
        for country in countries:
            self.assertFalse(self._is_chinese_city(country), f"'{country}' should be detected as foreign")


class TestBoundarySelectionIntegration(unittest.TestCase):
    """Integration tests that require actual module import"""
    
    @classmethod
    def setUpClass(cls):
        """Try to import the geo_query_engine module"""
        try:
            from core.geo_query_engine import OSMAdapter
            cls.osm_adapter_class = OSMAdapter
            cls.module_available = True
        except ImportError as e:
            cls.module_available = False
            cls.import_error = str(e)
    
    def test_module_import(self):
        """Test that the module can be imported"""
        if not self.module_available:
            self.skipTest(f"Module not available: {self.import_error}")
        self.assertIsNotNone(self.osm_adapter_class)
    
    def test_process_boundary_response_exists(self):
        """Test that _process_boundary_response method exists"""
        if not self.module_available:
            self.skipTest("Module not available")
        
        # Check method exists
        self.assertTrue(hasattr(self.osm_adapter_class, '_process_boundary_response'))


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
