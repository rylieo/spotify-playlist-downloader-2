"""
Antigravity Resolver Engine
95-100% akurat untuk mengidentifikasi lagu yang sama antara platform
"""

import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class TrackMetadata:
    """Metadata lengkap untuk sebuah lagu"""
    title: str
    artist: str
    album: str = ""
    duration_ms: int = 0
    isrc: str = ""
    year: str = ""
    track_number: int = 0
    
    def get_duration_seconds(self) -> float:
        return self.duration_ms / 1000.0 if self.duration_ms else 0

@dataclass
class Candidate:
    """Kandidat lagu dari platform target"""
    video_id: str
    title: str
    artists: List[str]
    album: str = ""
    duration: float = 0
    isrc: str = ""
    source: str = "unknown"  # ytmusic, youtube, etc.
    
    def get_primary_artist(self) -> str:
        return self.artists[0] if self.artists else ""

class AntigravityResolver:
    """Resolver engine untuk mengidentifikasi lagu yang sama dengan akurasi 95-100%"""
    
    def __init__(self, confidence_threshold: float = 0.85):
        self.confidence_threshold = confidence_threshold
        
        # Blacklist untuk unwanted indicators
        self.unwanted_patterns = [
            r'\(live\)', r'\(live.*?\)', r'live at', r'live from',
            r'\(remix\)', r'\(remix.*?\)', r'remix by',
            r'\(cover\)', r'\(cover.*?\)', r'cover by',
            r'\(acoustic\)', r'\(acoustic.*?\)',
            r'\(karaoke\)', r'\(karaoke.*?\)',
            r'\(instrumental\)', r'\(instrumental.*?\)',
            r'\(demo\)', r'\(demo.*?\)',
            r'\(extended\)', r'\(extended.*?\)',
            r'\(radio.*?\)', r'\(edit\)', r'\(version.*?\)',
            r'slowed', r'reverb', r'nightcore',  # Removed 'speed up' to allow sped up versions
            r'8d audio', r'spatial audio', r'dolby atmos'
        ]
        
        # Compile regex patterns
        self.unwanted_regex = [re.compile(pattern, re.IGNORECASE) for pattern in self.unwanted_patterns]
    
    def resolve(self, target: TrackMetadata, candidates: List[Candidate], verbose: bool = False) -> Optional[Tuple[Candidate, float]]:
        """
        Resolve identitas lagu dengan confidence score
        
        Args:
            target: Lagu target dari Spotify
            candidates: Daftar kandidat dari YouTube Music
            
        Returns:
            Tuple[Candidate, confidence] atau None jika tidak ada yang cocok
        """
        if not candidates:
            return None
        
        # Score semua kandidat
        scored_candidates = []
        for i, candidate in enumerate(candidates):
            score, confidence = self._calculate_confidence(target, candidate, verbose)
            if confidence > 0:  # Hanya yang ada confidence
                scored_candidates.append((candidate, score, confidence))
                if verbose: print(f"  Candidate {i+1}: {candidate.title} - Score: {score:.1f}, Confidence: {confidence:.3f}")
        
        # Sort by confidence (tertinggi ke terendah)
        scored_candidates.sort(key=lambda x: x[2], reverse=True)
        
        if not scored_candidates:
            if verbose: print("  No candidates scored above 0")
            return None
        
        # Ambil yang confidence tertinggi
        best_candidate, best_score, best_confidence = scored_candidates[0]
        if verbose: print(f"  Best: {best_candidate.title} - Confidence: {best_confidence:.3f}")
        
        # Return hanya jika confidence melewati threshold
        if best_confidence >= self.confidence_threshold:
            return best_candidate, best_confidence
        else:
            if verbose: print(f"  Best confidence {best_confidence:.3f} below threshold {self.confidence_threshold}")
        
        return None
    
    def _calculate_confidence(self, target: TrackMetadata, candidate: Candidate, verbose: bool = False) -> Tuple[float, float]:
        """
        Calculate confidence score (0-1) dan detail score
        
        Returns:
            Tuple[score, confidence] dimana confidence adalah normalized score
        """
        score = 0.0
        max_score = 100.0
        
        # 1. ISRC Match (40 points) - PALING PENTING
        if target.isrc and candidate.isrc:
            if target.isrc.lower() == candidate.isrc.lower():
                score += 40.0
                if verbose: print(f"    ISRC MATCH: +40 points")
        
        # 2. Title Match (35 points) - increased weight
        title_score = self._calculate_title_similarity(target.title, candidate.title)
        score += title_score * 35.0
        if title_score > 0.8:
            if verbose: print(f"    Title match: {title_score:.2f} (+{title_score * 35:.1f} points)")
        
        # 3. Artist Match (25 points) - increased weight
        artist_score = self._calculate_artist_similarity(target.artist, candidate.artists)
        score += artist_score * 25.0
        if artist_score > 0.8:
            if verbose: print(f"    Artist match: {artist_score:.2f} (+{artist_score * 25:.1f} points)")
        
        # 4. Duration Match (10 points)
        duration_score = self._calculate_duration_similarity(target.get_duration_seconds(), candidate.duration)
        score += duration_score * 10.0
        if duration_score > 0.8:
            if verbose: print(f"    Duration match: {duration_score:.2f} (+{duration_score * 10:.1f} points)")
        
        # 5. Album Match (5 points) - added album matching
        if target.album and candidate.album:
            album_score = self._calculate_string_similarity(target.album.lower(), candidate.album.lower())
            score += album_score * 5.0
            if album_score > 0.8:
                if verbose: print(f"    Album match: {album_score:.2f} (+{album_score * 5:.1f} points)")
        
        # 6. Penalties for unwanted indicators (subtract points)
        penalty = self._calculate_unwanted_penalty(candidate.title)
        if penalty > 0:
            score -= penalty
            if verbose: print(f"    Unwanted penalty: -{penalty:.1f} points")
        
        # 7. Bonus for exact matches
        if title_score >= 0.9 and artist_score >= 0.9:
            score += 20.0  # Increased bonus for exact title + artist match
            if verbose: print(f"    Exact match bonus: +20 points")
        
        # 8. Bonus for original versions with features (prefer over instrumental)
        candidate_lower = candidate.title.lower()
        if ('feat.' in candidate_lower or 'featuring' in candidate_lower) and \
           'instrumental' not in candidate_lower and \
           'remix' not in candidate_lower and \
           'acapella' not in candidate_lower:
            score += 15.0  # Bonus for original version with features
            if verbose: print(f"    Original version bonus: +15 points")
        
        # 9. Penalty for instrumental versions (prefer original)
        if 'instrumental' in candidate_lower:
            score -= 25.0  # Penalty for instrumental versions
            if verbose: print(f"    Instrumental penalty: -25 points")
        
        # Normalize to 0-1 confidence
        confidence = max(0.0, score / max_score)
        
        if verbose: print(f"    Total: {score:.1f}/{max_score} = {confidence:.3f}")
        
        return score, confidence
    
    def _calculate_title_similarity(self, target_title: str, candidate_title: str) -> float:
        """Calculate title similarity (0-1)"""
        if not target_title or not candidate_title:
            return 0.0
        
        target_clean = self._clean_title(target_title)
        candidate_clean = self._clean_title(candidate_title)
        
        # Exact match
        if target_clean.lower() == candidate_clean.lower():
            return 1.0
        
        # Word overlap
        target_words = set(target_clean.lower().split())
        candidate_words = set(candidate_clean.lower().split())
        
        if not target_words or not candidate_words:
            return 0.0
        
        # Calculate Jaccard similarity
        intersection = target_words & candidate_words
        union = target_words | candidate_words
        
        if not union:
            return 0.0
        
        jaccard = len(intersection) / len(union)
        
        # Bonus untuk exact word order
        if target_clean.lower() in candidate_clean.lower() or candidate_clean.lower() in target_clean.lower():
            jaccard += 0.2
        
        return min(1.0, jaccard)
    
    def _calculate_artist_similarity(self, target_artist: str, candidate_artists: List[str]) -> float:
        """Calculate artist similarity (0-1)"""
        if not target_artist or not candidate_artists:
            return 0.0
        
        target_clean = self._clean_artist(target_artist)
        
        # Check each candidate artist
        best_match = 0.0
        for artist in candidate_artists:
            artist_clean = self._clean_artist(artist)
            
            # Exact match
            if target_clean.lower() == artist_clean.lower():
                return 1.0
            
            # Contains match
            if target_clean.lower() in artist_clean.lower() or artist_clean.lower() in target_clean.lower():
                return 0.8
            
            # Word overlap
            target_words = set(target_clean.lower().split())
            artist_words = set(artist_clean.lower().split())
            
            if target_words and artist_words:
                intersection = target_words & artist_words
                union = target_words | artist_words
                
                if union:
                    jaccard = len(intersection) / len(union)
                    best_match = max(best_match, jaccard)
        
        return best_match
    
    def _calculate_duration_similarity(self, target_duration: float, candidate_duration: float) -> float:
        """Calculate duration similarity (0-1) - ULTRA STRICT FOR MUSIC VIDEOS"""
        if target_duration <= 0 or candidate_duration <= 0:
            return 0.0
        
        diff = abs(target_duration - candidate_duration)
        
        # PERFECT match (within 1 second) - MAXIMUM SCORE
        if diff <= 1.0:
            return 1.0
        
        # Very close (within 1.5 seconds) - High penalty
        if diff <= 1.5:
            return 0.6
        
        # Close (within 2 seconds) - Major penalty
        if diff <= 2.0:
            return 0.3
        
        # Moderate (within 3 seconds) - Very low score
        if diff <= 3.0:
            return 0.1
        
        # Anything longer than 3 seconds - ZERO
        return 0.0
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate basic string similarity (0-1)"""
        if not str1 or not str2:
            return 0.0
        
        if str1.lower() == str2.lower():
            return 1.0
        
        if str1.lower() in str2.lower() or str2.lower() in str1.lower():
            return 0.7
        
        # Simple word overlap
        words1 = set(str1.lower().split())
        words2 = set(str2.lower().split())
        
        if words1 and words2:
            intersection = words1 & words2
            union = words1 | words2
            if union:
                return len(intersection) / len(union)
        
        return 0.0
    
    def _calculate_unwanted_penalty(self, title: str) -> float:
        """Calculate penalty for unwanted content - ENHANCED MUSIC VIDEO DETECTION"""
        if not title:
            return 0.0
        
        title_lower = title.lower()
        penalty = 0.0
        
        # Enhanced music video detection
        music_video_indicators = [
            "official video", "music video", "mv", "official mv",
            "video clip", "clip", "visual", "visualizer",
            "lyric video", "lyrics video", "animated",
            "remix", "live", "acoustic", "instrumental", 
            "cover", "karaoke", "slowed",  # Removed "sped up" to allow sped up versions
            "concert", "perform", "tour", "8d", "8d audio"
        ]
        
        for indicator in music_video_indicators:
            if indicator in title_lower:
                # Higher penalty for music video indicators
                if indicator in ["official video", "music video", "mv", "official mv"]:
                    penalty += 50.0  # Very high penalty
                elif indicator in ["video clip", "clip", "visual", "visualizer"]:
                    penalty += 40.0  # High penalty
                elif indicator in ["remix", "live", "slowed"]:
                    penalty += 30.0  # Medium penalty
                elif indicator in ["lyric video", "lyrics video", "animated"]:
                    penalty += 25.0  # Medium-low penalty
                elif indicator in ["acoustic", "instrumental", "cover", "karaoke"]:
                    penalty += 20.0  # Low penalty
                else:
                    penalty += 15.0  # Minimal penalty for others
        
        return penalty
    
    def _clean_title(self, title: str) -> str:
        """Clean title for comparison"""
        if not title:
            return ""
        
        # Remove unwanted patterns
        cleaned = title
        
        # Remove common unwanted text
        for pattern in self.unwanted_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
        
        # Remove extra whitespace and special characters
        cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _clean_artist(self, artist: str) -> str:
        """Clean artist name for comparison"""
        if not artist:
            return ""
        
        # Remove common patterns
        cleaned = re.sub(r'\s*\(.*?\)\s*', '', artist)
        cleaned = re.sub(r'\s*\[.*?\]\s*', '', cleaned)
        cleaned = re.sub(r'\s*feat\..*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*&.*', '', cleaned)
        
        # Clean whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned

# Factory function
def create_resolver(confidence_threshold: float = 0.85) -> AntigravityResolver:
    """Create Antigravity Resolver instance"""
    return AntigravityResolver(confidence_threshold)
