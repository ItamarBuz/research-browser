"""Passages as the parser produced them from real arXiv papers (trimmed), plus Hebrew samples.

Sources: LIGO, "Observation of Gravitational Waves from a Binary Black Hole Merger" (2016);
Gershuni & Pinter, "Restoring Hebrew Diacritics Without a Dictionary" (2021); Vaswani et al.,
"Attention Is All You Need" (2017); a 2021 paper on minimum wages in concentrated labor
markets. The odd spacing ("Stra ́ nˇak") is how PDFium extracts accented names.
"""

# --- author and affiliation lists ------------------------------------------------------

LIGO_AUTHOR_LIST = (
    "B. P. Abbott,1 R. Abbott,1 T. D. Abbott,2 M. R. Abernathy,1 F. Acernese,3,4 K. Ackley,5 "
    "C. Adams,6 T. Adams,7 P. Addesso,3 R. X. Adhikari,1 V. B. Adya,8 C. Affeldt,8 M. Agathos,9 "
    "K. Agatsuma,9 N. Aggarwal,10 O. D. Aguiar,11 L. Aiello,12,13 A. Ain,14 P. Ajith,15 "
    "B. Allen,8,16,17 A. Allocca,18,19 P. A. Altin,20 S. B. Anderson,1 W. G. Anderson,16 "
    "K. Arai,1 M. A. Arain,5 M. C. Araya,1 C. C. Arceneaux,21 J. S. Areeda,22 N. Arnaud,23 "
    "K. G. Arun,24 S. Ascenzi,25,13 G. Ashton,26 M. Ast,27 S. M. Aston,6 P. Astone,28"
)
"""Pages 11-13 of the LIGO paper; returned as the best passages for "what were the masses of
the two black holes that merged?" asked in Hebrew."""

LIGO_AFFILIATIONS = (
    "10LIGO, Massachusetts Institute of Technology, Cambridge, Massachusetts 02139, USA "
    "11Instituto Nacional de Pesquisas Espaciais, 12227-010 São José dos Campos, São Paulo, "
    "Brazil 12INFN, Gran Sasso Science Institute, I-67100 L’Aquila, Italy 13INFN, Sezione di "
    "Roma Tor Vergata, I-00133 Roma, Italy 14Inter-University Centre for Astronomy and "
    "Astrophysics, Pune 411007, India 15International Centre for Theoretical Sciences, Tata "
    "Institute of Fundamental Research, Bangalore 560012, India 16University of "
    "Wisconsin-Milwaukee, Milwaukee, Wisconsin 53201, USA 17Leibniz Universität Hannover, "
    "D-30167 Hannover, Germany 18Università di Pisa, I-56127 Pisa, Italy"
)

ATTENTION_TITLE_BLOCK = (
    "Provided proper attribution is provided, Google hereby grants permission to reproduce the "
    "tables and figures in this paper solely for use in journalistic or scholarly works. "
    "Attention Is All You Need Ashish Vaswani∗ Google Brain avaswani@google.com Noam Shazeer∗ "
    "Google Brain noam@google.com Niki Parmar∗ Google Research nikip@google.com Jakob "
    "Uszkoreit∗ Google Research usz@google.com Llion Jones∗ Google Research llion@google.com "
    "Abstract The dominant sequence transduction models are based on complex recurrent or "
    "convolutional neural networks that include an encoder and a decoder. The best performing "
    "models also connect the encoder and decoder through an attention mechanism."
)
"""Authors and the abstract in one passage: the abstract must stay searchable."""

# --- reference lists -------------------------------------------------------------------

LIGO_REFERENCES = (
    "[18] C. T. Bolton, Nature (London) 240, 124 (1972). [19] J. Casares and P. G. Jonker, "
    "Space Sci. Rev. 183, 223 (2014). [20] R. A. Hulse and J. H. Taylor, Astrophys. J. 195, L51 "
    "(1975). [21] J. H. Taylor and J. M. Weisberg, Astrophys. J. 253, 908 (1982). [22] W. Press "
    "and K. Thorne, Annu. Rev. Astron. Astrophys. 10, 335 (1972). [23] J. Weber, Phys. Rev. "
    "117, 306 (1960). [24] P. Astone et al., Phys. Rev. D 82, 022003 (2010)."
)

DIACRITICS_REFERENCES_HEADING = (
    "Acknowledgments We would like to thank Avi Shmidman for details about Dicta’s Nakdan and "
    "other suggestions. We thank Sara Gershuni for lengthy and fruitful discussions, and for "
    "her linguistic insights and advice. We thank Yoav Goldberg, Reut Tsarfaty, Ian Stewart, "
    "Sarah Wiegreffe, Kyle Gorman and many anonymous reviewers for their comments and "
    "suggestions in discussions and on earlier drafts. References Gheith Abandah, Alex Graves, "
    "Balkees Al-Shagoor, Alaa Arabiyat, Fuad Jamour, and Majid Al-Taee. 2015. Automatic "
    "diacritization of Arabic text using recurrent neural networks. International Journal on "
    "Document Analysis and Recognition (IJDAR), 18:183–197. Salim Abu-Rabia. 2001. The role of "
    "vowels in reading semitic scripts: Data from Arabic and Hebrew. Reading and Writing, "
    "14(1-2):39–59. Yonatan Belinkov and James Glass. 2015."
)

DIACRITICS_REFERENCES = (
    "Jakub Naplava, Milan Straka, Pavel Stra ́ nˇak, and Jan ́ Hajic. 2018. ˇ Diacritics "
    "restoration using neural networks. In Proceedings of the Eleventh International Conference "
    "on Language Resources and Evaluation (LREC 2018), Miyazaki, Japan. European Language "
    "Resources Association (ELRA). Barbara Plank, Anders Søgaard, and Yoav Goldberg. 2016. "
    "Multilingual part-of-speech tagging with bidirectional long short-term memory models and "
    "auxiliary loss. In Proceedings of the 54th Annual Meeting of the Association for "
    "Computational Linguistics (Volume 2: Short Papers), pages 412–418, Berlin, Germany. "
    "Association for Computational Linguistics. Danny Shacham and Shuly Wintner. 2007. "
    "Morphological disambiguation of Hebrew: A case study in classifier combination."
)
"""Page 7 of the diacritics paper; returned first for "automatic restoration of Hebrew
diacritics with a neural network" asked in Hebrew. ACL-style entries have wordy titles and
venues, so they are only recognised inside a references section."""

DIACRITICS_REFERENCES_CONTINUED = (
    "In Proceedings of the 2007 Joint Conference on Empirical Methods in Natural Language "
    "Processing and Computational Natural Language Learning (EMNLP-CoNLL), pages 439–447, "
    "Prague, Czech Republic. Association for Computational Linguistics. Avi Shmidman, Shaltiel "
    "Shmidman, Moshe Koppel, and Yoav Goldberg. 2020. Nakdan: Professional Hebrew diacritizer. "
    "In Proceedings of the 58th Annual Meeting of the Association for Computational "
    "Linguistics: System Demonstrations, pages 197– 203, Online. Association for Computational "
    "Linguistics. Leslie N Smith. 2017. Cyclical learning rates for training neural networks. "
    "In 2017 IEEE Winter Conference on Applications of Computer Vision (WACV), pages 464–472. "
    "IEEE."
)

DIACRITICS_APPENDIX = (
    "A Full Script Reconciliation We apply the following resolution tactics for added letters "
    "in undotted text: (a) We almost never remove or add letters to the original text (unless "
    "it is completely undiacritizable). (b) We keep dagesh in letters that follow a shuruk "
    "which replaces a kubuts, and similarly for yod (hirik male replacing hirik haser). (c) "
    "When we have double vav or double yod, the second letter is usually left undotted, except "
    "when it is impossible to have the correct vocalization this way."
)

APA_REFERENCES = (
    "Azar, J., Marinescu, I., and Steinbaum, M. I. (2022). Labor Market Concentration. Journal "
    "of Human Resources 57 (S), pp. 167–199. Bachmann, R., Bauer, T. K., and Frings, H. (2014). "
    "Minimum Wages as a Barrier to Entry: Evidence from Germany. LABOUR 28 (3), pp. 338–357. "
    "Bassanini, A., Batut, C., and Caroli, E. (2023). Labor Market Concentration and Wages: "
    "Incumbents versus New Hires. Labour Economics 81, No. 102338."
)

# --- body text that must stay searchable -----------------------------------------------

LIGO_MASSES_TABLE = (
    "Primary black hole mass 36þ5 −4M⊙ Secondary black hole mass 29þ4 −4M⊙ Final black hole "
    "mass 62þ4 −4M⊙ Final black hole spin 0.67þ0.05 −0.07 Luminosity distance 410þ160 −180 Mpc "
    "Source redshift z 0.09þ0.03 −0.04"
)
"""The answer to the masses question: a table, so almost no function words."""

LIGO_INTRODUCTION = (
    "Also in 1916, Schwarzschild published a solution for the field equations [4] that was "
    "later understood to describe a black hole [5,6], and in 1963 Kerr generalized the solution "
    "to rotating black holes [7]. Starting in the 1970s theoretical work led to the "
    "understanding of black hole quasinormal modes [8–10], and in the 1990s higher-order "
    "post-Newtonian calculations [11] preceded extensive analytical studies of relativistic "
    "two-body dynamics [12,13]."
)

RELATED_WORK = (
    "Dictionary-less Arabic diacritization has been attempted using a 3-layer Bi-LSTM "
    "(Belinkov and Glass, 2015). Abandah et al. (2015) use a Bi-LSTM where characters are "
    "assigned either one or more diacritic symbols. Our system differs from theirs by virtue of "
    "separating the diacritization categories. Mubarak et al. (2019) tackled Arabic "
    "diacritization as a sequence-to-sequence problem, tasking the model with reproducing the "
    "characters as well as the marks. Zalmout and Habash (2017) have made the case against "
    "RNN-only systems, arguing for the importance of morphological analyzers in Arabic NLP."
)

TABLE_CITING_PRIOR_WORK = (
    "Table 4: The Transformer generalizes well to English constituency parsing (Results are on "
    "Section 23 of WSJ) Parser Training WSJ 23 F1 Vinyals & Kaiser el al. (2014) [37] WSJ only, "
    "discriminative 88.3 Petrov et al. (2006) [29] WSJ only, discriminative 90.4 Zhu et al. "
    "(2013) [40] WSJ only, discriminative 90.4 Dyer et al. (2016) [8] WSJ only, discriminative "
    "91.7 Transformer (4 layers) WSJ only, discriminative 91.3 Huang & Harper (2009) [14] "
    "semi-supervised 91.3 McClosky et al. (2006) [26] semi-supervised 92.1"
)

DATA_DESCRIPTION_WITH_YEARS = (
    "For the years 1999-2002 and 2003-2007, I make use of earlier 1993 NACE-5 and 2003 NACE-5 "
    "codes to determine the minimum wage sectors: electrical trade (1993/2003 NACE-5: 4531.0), "
    "roofing (1993/2003 NACE-5: 4522.1), painting and varnishing (1993/2003 NACE-5: 4544.1), "
    "commercial cleaning (1993/2003 NACE-5: 7470.1/7470.3-4), nursing care (1993/2003 NACE-5: "
    "8531.5/8532.6), security (1993/2003 NACE-5: 7460.2), temporary work (1993/2003 NACE-5: "
    "7450.2), scaffolding (1993/2003 NACE-5: 4525.4)."
)

# --- Hebrew ------------------------------------------------------------------------------

HEBREW_PROSE = (
    "מחקר זה בוחן את השפעתו של מחסור חלקי בשינה על הקישוריות בין אזורי המוח. ארבעים משתתפים "
    "בריאים עברו סריקת דימות לאחר לילה של שינה מלאה ולאחר לילה שבו ישנו ארבע שעות בלבד. מצאנו "
    "כי הקישוריות ברשת ברירת המחדל ירדה באופן מובהק לאחר המחסור, וכי הירידה הייתה קשורה "
    "לשינויים במצב הרוח. ממצאים אלה מצטרפים למחקרים קודמים (כהן ולוי, 2019; Smith et al., "
    "2020) ומרמזים על כך שגם מחסור קצר בשינה משבש את האיזון בין הרשתות."
)

HEBREW_REFERENCES = (
    "מקורות בן-חיים, ז' (1992). דקדוק הלשון העברית. ירושלים: מוסד ביאליק. גרשוני, א' ופינטר, "
    "י' (2022). שחזור ניקוד בעברית ללא מילון. בתוך: ד' כהן (עורך), מחקרים בבלשנות חישובית, "
    "עמ' 45–67. תל אביב: הוצאת האוניברסיטה הפתוחה. לוי, ר', כהן, ש' ומזרחי, ת' (2018). שינה, "
    "זיכרון ורגש בקרב מתבגרים. פסיכולוגיה עברית, 12(3), 201–219."
)

MIXED_REFERENCES = (
    "פרידמן, ש' (2015). תולדות הלוח העברי. ירושלים: מאגנס. Dershowitz, N. and Reingold, E. M. "
    "(1997). Calendrical Calculations. Cambridge University Press. רוזן, ד' ואברהם, נ' (2011). "
    "חישובי מולד ודחיות. תרביץ 80(2), 233–251."
)
"""Hebrew papers cite English sources in the same list."""
