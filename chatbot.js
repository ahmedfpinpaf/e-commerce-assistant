/**
 * LLM-Free Item-First Conversational Product Search Assistant
 * With Currency Detection (PKR / USD), Live Exchange Rate Conversion, and Explicit Approval.
 *
 * Connected directly to catalog_raw.json (or window.PRODUCTS_DATA).
 * Strictly NO LLM, NO Generative AI.
 */

class CurrencyManager {
  constructor() {
    // Current market rate: ~277.16 PKR per USD (0.003608 USD per PKR)
    this.rateUsdPerPkr = 0.003608;
    this.isLive = false;
    this.fetchLiveRate();
  }

  async fetchLiveRate() {
    // 1. Try public open exchange rate API
    try {
      if (typeof fetch === 'function') {
        const res = await fetch('https://open.er-api.com/v6/latest/PKR');
        if (res.ok) {
          const data = await res.json();
          if (data && data.rates && data.rates.USD) {
            this.rateUsdPerPkr = data.rates.USD;
            this.isLive = true;
            return;
          }
        }
      }
    } catch (e) {
      // 2. Try local FastAPI proxy endpoint
      try {
        if (typeof fetch === 'function') {
          const resLocal = await fetch('/api/exchange-rate');
          if (resLocal.ok) {
            const dataLocal = await resLocal.json();
            if (dataLocal && dataLocal.rate_usd) {
              this.rateUsdPerPkr = dataLocal.rate_usd;
              this.isLive = true;
            }
          }
        }
      } catch (err) {}
    }
  }

  convertPkrToUsd(pkrAmount) {
    if (!pkrAmount || isNaN(pkrAmount)) return 0;
    const usd = pkrAmount * this.rateUsdPerPkr;
    if (usd >= 10) {
      return Math.round(usd);
    }
    return Math.round(usd * 100) / 100;
  }
}

class CatalogAnalyzer {
  constructor(catalog) {
    this.catalog = Array.isArray(catalog) ? catalog : [];
    this.categories = new Set();
    this.brandsByCategory = {};
    this.allBrands = new Set();
    this.priceBoundsByCategory = {};
    this.categoryProfiles = {};

    this.analyze();
  }

  analyze() {
    this.catalog.forEach(item => {
      const cat = (item.category || '').trim().toLowerCase();
      if (!cat) return;

      this.categories.add(cat);

      if (!this.brandsByCategory[cat]) {
        this.brandsByCategory[cat] = new Set();
        this.priceBoundsByCategory[cat] = { min: Infinity, max: 0 };
        this.categoryProfiles[cat] = {
          hasBrands: false,
          itemsCount: 0
        };
      }

      this.categoryProfiles[cat].itemsCount += 1;

      // Brand
      const brand = (item.brand || '').trim();
      if (brand && brand.toLowerCase() !== 'n/a' && brand.toLowerCase() !== 'none') {
        this.brandsByCategory[cat].add(brand);
        this.allBrands.add(brand);
        this.categoryProfiles[cat].hasBrands = true;
      }

      // Price (Catalog prices are in USD)
      const price = typeof item.price === 'number' ? item.price : parseFloat(item.price);
      if (!isNaN(price) && price > 0) {
        if (price < this.priceBoundsByCategory[cat].min) this.priceBoundsByCategory[cat].min = price;
        if (price > this.priceBoundsByCategory[cat].max) this.priceBoundsByCategory[cat].max = price;
      }
    });
  }

  getCategories() {
    return Array.from(this.categories).sort();
  }

  getBrands(category = null) {
    if (category && this.brandsByCategory[category.toLowerCase()]) {
      return Array.from(this.brandsByCategory[category.toLowerCase()]).sort();
    }
    return Array.from(this.allBrands).sort();
  }
}

class RuleBasedParser {
  constructor(analyzer) {
    this.analyzer = analyzer;

    // Common synonyms and aliases for catalog items/categories
    this.categoryAliases = {
      'laptop': 'laptops',
      'laptops': 'laptops',
      'notebook': 'laptops',
      'notebooks': 'laptops',
      'computer': 'laptops',
      'computers': 'laptops',
      'pc': 'laptops',

      'mobile': 'smartphones',
      'mobiles': 'smartphones',
      'phone': 'smartphones',
      'phones': 'smartphones',
      'smartphone': 'smartphones',
      'smartphones': 'smartphones',
      'cellphone': 'smartphones',

      'beauty': 'beauty',
      'makeup': 'beauty',
      'cosmetic': 'beauty',
      'cosmetics': 'beauty',
      'mascara': 'beauty',
      'lipstick': 'beauty',

      'fragrance': 'fragrances',
      'fragrances': 'fragrances',
      'perfume': 'fragrances',
      'perfumes': 'fragrances',
      'cologne': 'fragrances',
      'scent': 'fragrances',

      'furniture': 'furniture',
      'sofa': 'furniture',
      'couch': 'furniture',
      'bed': 'furniture',
      'chair': 'furniture',
      'table': 'furniture',

      'grocery': 'groceries',
      'groceries': 'groceries',
      'food': 'groceries',
      'snack': 'groceries',

      'shirt': 'mens-shirts',
      'shirts': 'mens-shirts',
      'tshirt': 'mens-shirts',
      'dress': 'womens-dresses',
      'dresses': 'womens-dresses',
      'clothing': "men's clothing",
      'clothes': "men's clothing",

      'shoe': 'mens-shoes',
      'shoes': 'mens-shoes',
      'sneaker': 'mens-shoes',
      'sneakers': 'mens-shoes',

      'watch': 'mens-watches',
      'watches': 'mens-watches',

      'bag': 'womens-bags',
      'bags': 'womens-bags',
      'backpack': 'womens-bags',

      'jewelry': 'jewelery',
      'jewelery': 'jewelery',

      'electronic': 'electronics',
      'electronics': 'electronics',
      'tablet': 'tablets',
      'tablets': 'tablets'
    };
  }

  parseNumber(str, unit) {
    if (!str) return null;
    let clean = str.replace(/,/g, '');
    let val = parseFloat(clean);
    if (isNaN(val)) return null;
    if (unit && unit.toLowerCase().startsWith('k')) {
      val *= 1000;
    } else if (unit && unit.toLowerCase().startsWith('m')) {
      val *= 1000000;
    }
    return val;
  }

  extractBudgetAndCurrency(text) {
    const lower = text.toLowerCase().trim();
    let amount = null;
    let currency = null;

    // 1. Detect explicit currency keywords
    if (/\b(pkr|rs|rupees|rupee|rs\.)\b/i.test(lower)) {
      currency = 'PKR';
    } else if (/(\$|\busd\b|\bdollars\b|\bdollar\b)/i.test(lower)) {
      currency = 'USD';
    }

    // 2. Extract numeric amount
    // Range: "between 500 and 1500", "500 to 1500"
    const rangeMatch = lower.match(/(?:between|from)?\s*[\$£€]?(?:pkr|rs)?\s*([0-9]+(?:[.,][0-9]+)?)\s*(k|m)?\s*(?:and|to|-)\s*[\$£€]?(?:pkr|rs)?\s*([0-9]+(?:[.,][0-9]+)?)\s*(k|m)?/i);
    if (rangeMatch) {
      amount = this.parseNumber(rangeMatch[3], rangeMatch[4]);
    } else {
      // Bound check: "under 150k PKR", "below 150000", "budget 150,000", "max 2000"
      const boundMatch = lower.match(/(?:under|below|less\s+than|max|maximum|budget|up\s+to|at\s+most|within)\s*(?:of|is|:)?\s*[\$£€]?(?:pkr|rs)?\s*([0-9]+(?:[.,][0-9]+)?)\s*(k|m)?/i);
      if (boundMatch) {
        amount = this.parseNumber(boundMatch[1], boundMatch[2]);
      } else {
        // Standalone number with optional currency: "$1000", "150000 PKR", "150,000", "150k"
        const numMatch = lower.match(/(?:[\$£€]|pkr|rs)?\s*([0-9]+(?:[.,][0-9]+)?)\s*(k|m)?(?:\s*(?:pkr|rs|rupees|usd|dollars))?/i);
        if (numMatch && numMatch[1]) {
          amount = this.parseNumber(numMatch[1], numMatch[2]);
        }
      }
    }

    return { amount, currency };
  }

  isApproval(text) {
    const clean = text.toLowerCase().trim().replace(/[.,!]/g, ' ');
    return /\b(yes|yep|yeah|ok|okay|sure|use it|correct|confirm|proceed|continue|thats fine|that is fine|agree|approved|fine)\b/i.test(clean) ||
           clean.includes('use this budget');
  }

  isRejection(text) {
    const clean = text.toLowerCase().trim().replace(/[.,!]/g, ' ');
    return /\b(no|nope|nah|change|change it|change budget|not correct|wrong|too much|too high|cancel|dont use|do not use)\b/i.test(clean);
  }

  extractCurrencyChoice(text) {
    const clean = text.toLowerCase().trim();
    if (/\b(pkr|rupees|rupee|rs|pakistani)\b/i.test(clean)) {
      return 'PKR';
    }
    if (/\b(usd|dollars|dollar|\$|us dollars)\b/i.test(clean)) {
      return 'USD';
    }
    return null;
  }

  extractCategory(text) {
    const lower = text.toLowerCase();

    // Check exact catalog categories
    const catalogCats = this.analyzer.getCategories();
    for (const cat of catalogCats) {
      const regex = new RegExp(`\\b${cat.replace(/[-']/g, '[-\\s\']')}\\b`, 'i');
      if (regex.test(lower)) {
        return cat;
      }
    }

    // Check aliases
    for (const [alias, realCat] of Object.entries(this.categoryAliases)) {
      const regex = new RegExp(`\\b${alias}\\b`, 'i');
      if (regex.test(lower)) {
        return realCat;
      }
    }

    return null;
  }

  extractBrands(text, category = null) {
    const brands = this.analyzer.getBrands(category);
    const matched = [];
    const lower = text.toLowerCase();

    for (const b of brands) {
      const regex = new RegExp(`\\b${b.replace(/[-']/g, '[-\\s\']')}\\b`, 'i');
      if (regex.test(lower)) {
        matched.push(b);
      }
    }

    if (matched.length === 0 && category) {
      const allBrands = this.analyzer.getBrands();
      for (const b of allBrands) {
        const regex = new RegExp(`\\b${b.replace(/[-']/g, '[-\\s\']')}\\b`, 'i');
        if (regex.test(lower)) {
          matched.push(b);
        }
      }
    }

    if (matched.length === 1) return matched[0];
    if (matched.length > 1) return matched;
    return null;
  }

  extractSpecs(text) {
    const specs = {};
    const lower = text.toLowerCase();

    // RAM: "16gb", "16 gigs", "16 gb ram"
    const ramMatch = lower.match(/\b([0-9]+)\s*(?:gb|gigs|gig|g)\s*(?:ram)?\b/);
    if (ramMatch) {
      specs.ram = `${ramMatch[1]}GB`;
    }

    // Storage: "512gb", "1tb", "256gb ssd"
    const storageMatch = lower.match(/\b([0-9]+)\s*(gb|tb)\s*(?:ssd|storage|hdd|rom)?\b/);
    if (storageMatch) {
      specs.storage = `${storageMatch[1]}${storageMatch[2].toUpperCase()}`;
    }

    // Processor: "i7", "core i7", "i5", "m1", "m2", "m1 pro", "ryzen"
    const procMatch = lower.match(/\b(core\s+i[3579]|i[3579]|m[12](?:\s+pro)?|ryzen\s*[0-9]?)\b/);
    if (procMatch) {
      specs.processor = procMatch[1].trim();
    }

    // Screen size: "14 inch", "13 inch", "15 inch"
    const screenMatch = lower.match(/\b([0-9]+(?:\.[0-9]+)?)\s*(?:inch|\"|-inch)\b/);
    if (screenMatch) {
      specs.screenSize = `${screenMatch[1]} Inch`;
    }

    return specs;
  }
}

class ProductFilterEngine {
  constructor(catalog) {
    this.catalog = Array.isArray(catalog) ? catalog : [];
  }

  filter(state) {
    return this.catalog.filter(p => {
      // Category Match
      if (state.category) {
        const pCat = (p.category || '').toLowerCase();
        if (pCat !== state.category.toLowerCase()) {
          return false;
        }
      }

      // Brand Match (supports single brand or array of brands)
      if (state.brand) {
        const pBrand = (p.brand || '').toLowerCase();
        if (Array.isArray(state.brand)) {
          const match = state.brand.some(b => pBrand === b.toLowerCase());
          if (!match) return false;
        } else {
          if (pBrand !== state.brand.toLowerCase()) {
            return false;
          }
        }
      }

      // Price Filter: Catalog prices are stored in USD!
      // Compare only when budget is confirmed!
      if (state.budget && state.budget.confirmed && state.budget.usd_amount !== null) {
        const price = typeof p.price === 'number' ? p.price : parseFloat(p.price);
        if (!isNaN(price) && price > state.budget.usd_amount) {
          return false;
        }
      }

      // Specs Match in title or description
      const fullText = `${p.title || ''} ${p.description || ''} ${(p.tags || []).join(' ')}`.toLowerCase();

      if (state.specs) {
        if (state.specs.processor) {
          const procClean = state.specs.processor.toLowerCase().replace(/\s+/g, '');
          if (!fullText.includes(state.specs.processor.toLowerCase()) && !fullText.includes(procClean)) {
            return false;
          }
        }
        if (state.specs.ram) {
          const ramClean = state.specs.ram.toLowerCase();
          if (!fullText.includes(ramClean)) {
            return false;
          }
        }
        if (state.specs.storage) {
          const stClean = state.specs.storage.toLowerCase();
          if (!fullText.includes(stClean)) {
            return false;
          }
        }
        if (state.specs.screenSize) {
          const scClean = state.specs.screenSize.toLowerCase();
          if (!fullText.includes(scClean)) {
            return false;
          }
        }
      }

      return true;
    });
  }

  diagnoseZeroResults(state) {
    if (state.category && state.brand && state.budget && state.budget.confirmed) {
      // Check if products exist for category & brand ignoring price limit
      const withBrandOnly = this.filter({ category: state.category, brand: state.brand, specs: state.specs, budget: { confirmed: false } });
      if (withBrandOnly.length > 0) {
        const lowestPrice = Math.min(...withBrandOnly.map(p => p.price));
        const brandName = Array.isArray(state.brand) ? state.brand.join(' or ') : state.brand;
        return `I found ${brandName} ${state.category}, but none are available under USD $${state.budget.usd_amount.toLocaleString()}. The lowest price is USD $${lowestPrice.toFixed(2)}.`;
      }
    }

    if (state.category && state.brand) {
      const withCatOnly = this.filter({ category: state.category });
      if (withCatOnly.length > 0) {
        const brandName = Array.isArray(state.brand) ? state.brand.join(' or ') : state.brand;
        return `I found products in ${state.category}, but none from brand "${brandName}".`;
      }
    }

    return "I couldn't find a product matching all of those specifications.";
  }

  getSimilarProducts(state) {
    if (state.category) {
      return this.catalog.filter(p => (p.category || '').toLowerCase() === state.category.toLowerCase()).slice(0, 5);
    }
    return this.catalog.slice(0, 5);
  }
}

class ChatbotAssistant {
  constructor(catalog) {
    this.catalog = catalog;
    this.analyzer = new CatalogAnalyzer(catalog);
    this.parser = new RuleBasedParser(this.analyzer);
    this.filterEngine = new ProductFilterEngine(catalog);
    this.currencyManager = new CurrencyManager();

    this.state = {
      category: null,
      brand: null,
      specs: {},
      budget: {
        raw_amount: null,
        currency: null,      // 'PKR' or 'USD' or null
        usd_amount: null,    // normalized USD amount
        confirmed: false     // must be true to allow catalog filtering
      },
      step: 'AWAIT_ITEM',
      pendingQuestion: null  // 'brand' | 'budget' | 'currency_choice' | 'budget_approval'
    };
  }

  reset() {
    this.state = {
      category: null,
      brand: null,
      specs: {},
      budget: {
        raw_amount: null,
        currency: null,
        usd_amount: null,
        confirmed: false
      },
      step: 'AWAIT_ITEM',
      pendingQuestion: null
    };
  }

  processMessage(userText) {
    const rawText = userText.trim();
    const lower = rawText.toLowerCase();

    // 1. Reset / Greeting Check
    if (/^(hi|hello|hey|restart|reset|start|new search)\b/i.test(lower)) {
      this.reset();
      return {
        reply: "Hello! What item or product are you looking for today?",
        products: []
      };
    }

    // 2. Handle Pending: CURRENCY_CHOICE
    // The user previously entered a number without currency, e.g. "150000"
    if (this.state.pendingQuestion === 'currency_choice') {
      const choice = this.parser.extractCurrencyChoice(rawText);
      if (!choice) {
        return {
          reply: "Please specify which currency your budget is in — PKR or USD:",
          chips: ['PKR', 'USD'],
          products: []
        };
      }

      this.state.budget.currency = choice;

      if (choice === 'PKR') {
        const usd = this.currencyManager.convertPkrToUsd(this.state.budget.raw_amount);
        this.state.budget.usd_amount = usd;
        this.state.budget.confirmed = false;
        this.state.pendingQuestion = 'budget_approval';

        return {
          reply: `PKR ${this.state.budget.raw_amount.toLocaleString()} is approximately USD $${usd.toLocaleString()} based on the current exchange rate.\n\nShould I use USD $${usd.toLocaleString()} as your maximum budget?`,
          chips: ['Yes, use this budget', 'Change budget'],
          products: []
        };
      } else {
        // USD choice
        this.state.budget.usd_amount = this.state.budget.raw_amount;
        this.state.budget.confirmed = false;
        this.state.pendingQuestion = 'budget_approval';

        return {
          reply: `Your maximum budget is USD $${this.state.budget.usd_amount.toLocaleString()}.\n\nShould I use USD $${this.state.budget.usd_amount.toLocaleString()} as your maximum budget?`,
          chips: ['Yes, use this budget', 'Change budget'],
          products: []
        };
      }
    }

    // 3. Handle Pending: BUDGET_APPROVAL
    // The user was asked: "Should I use USD $XXX as your maximum budget?"
    if (this.state.pendingQuestion === 'budget_approval') {
      if (this.parser.isApproval(rawText)) {
        this.state.budget.confirmed = true;
        this.state.pendingQuestion = null;

        // User confirmed! Now continue to product search or next spec
        return this.evaluateMatchesAndNextStep(`Great. I'll search using USD $${this.state.budget.usd_amount.toLocaleString()} as your confirmed budget.`);
      }

      if (this.parser.isRejection(rawText)) {
        this.state.budget.raw_amount = null;
        this.state.budget.currency = null;
        this.state.budget.usd_amount = null;
        this.state.budget.confirmed = false;
        this.state.pendingQuestion = 'budget';

        return {
          reply: "No problem. Please provide your preferred budget or tell me what you'd like to change.",
          products: []
        };
      }
    }

    // 4. Extract Category if not set
    const cat = this.parser.extractCategory(rawText);
    if (cat) {
      this.state.category = cat;
    }

    // 5. Extract Brand
    const effectiveCategory = this.state.category || cat;
    const brand = this.parser.extractBrands(rawText, effectiveCategory);
    if (brand) {
      this.state.brand = brand;
      if (this.state.pendingQuestion === 'brand') {
        this.state.pendingQuestion = null;
      }
    } else if (this.state.pendingQuestion === 'brand') {
      if (/^(any|no brand|skip|none|any brand|all brands|doesn't matter)$/i.test(lower)) {
        this.state.brand = null;
        this.state.pendingQuestion = null;
      }
    }

    // 6. Extract Technical Specs (RAM, Processor, Storage, Screen)
    const specs = this.parser.extractSpecs(rawText);
    if (Object.keys(specs).length > 0) {
      Object.assign(this.state.specs, specs);
    }

    // 7. Check if user provided/updated budget in this utterance
    const { amount, currency } = this.parser.extractBudgetAndCurrency(rawText);
    if (amount !== null) {
      // Invalidate previous confirmation!
      this.state.budget.raw_amount = amount;
      this.state.budget.confirmed = false;

      if (currency === 'PKR') {
        this.state.budget.currency = 'PKR';
        const usd = this.currencyManager.convertPkrToUsd(amount);
        this.state.budget.usd_amount = usd;
        this.state.pendingQuestion = 'budget_approval';

        return {
          reply: `PKR ${amount.toLocaleString()} is approximately USD $${usd.toLocaleString()} based on the current exchange rate.\n\nShould I use USD $${usd.toLocaleString()} as your maximum budget?`,
          chips: ['Yes, use this budget', 'Change budget'],
          products: []
        };
      } else if (currency === 'USD') {
        this.state.budget.currency = 'USD';
        this.state.budget.usd_amount = amount;
        this.state.pendingQuestion = 'budget_approval';

        return {
          reply: `Your maximum budget is USD $${amount.toLocaleString()}.\n\nShould I use USD $${amount.toLocaleString()} as your maximum budget?`,
          chips: ['Yes, use this budget', 'Change budget'],
          products: []
        };
      } else {
        // Currency is completely MISSING — must NOT assume!
        this.state.budget.currency = null;
        this.state.pendingQuestion = 'currency_choice';

        return {
          reply: "Sure. Which currency is your budget in — PKR or USD?",
          chips: ['PKR', 'USD'],
          products: []
        };
      }
    }

    // 8. If category is still unknown, prompt user
    if (!this.state.category) {
      this.state.step = 'AWAIT_ITEM';
      return {
        reply: "I couldn't identify that item in our catalog. Could you please specify what kind of product you are looking for? (e.g. laptop, mobile, beauty, shoes, fragrance)",
        products: []
      };
    }

    // 9. If user hasn't provided a budget at all yet and we are asking for budget:
    if (this.state.pendingQuestion === 'budget') {
      if (/^(any|no budget|skip|none|any price|doesn't matter)$/i.test(lower)) {
        this.state.budget.raw_amount = null;
        this.state.budget.usd_amount = null;
        this.state.budget.confirmed = true; // explicitly skipped
        this.state.pendingQuestion = null;
      }
    }

    return this.evaluateMatchesAndNextStep();
  }

  evaluateMatchesAndNextStep(prefixMessage = null) {
    // CRITICAL REQUIREMENT: If a budget was provided, IT MUST BE CONFIRMED before filtering!
    if (this.state.budget.raw_amount !== null && !this.state.budget.confirmed) {
      // Wait for approval
      return {
        reply: prefixMessage || "Please confirm your maximum budget before we proceed with the product search.",
        products: []
      };
    }

    // Run catalog filter
    const matches = this.filterEngine.filter(this.state);

    // SCENARIO 1: Exactly 1 Product Matches!
    if (matches.length === 1) {
      const p = matches[0];
      this.state.pendingQuestion = null;
      this.state.step = 'FOUND';

      let replyMsg = prefixMessage ? `${prefixMessage}\n\n` : '';
      replyMsg += "I found a matching product:";

      return {
        reply: replyMsg,
        isSingleMatch: true,
        product: p,
        products: [p]
      };
    }

    // SCENARIO 2: Multiple Products Match!
    if (matches.length > 1) {
      const brands = this.analyzer.getBrands(this.state.category);

      // Question A: Brand (if category has multiple brands and user hasn't specified)
      if (this.state.brand === null && brands.length > 1 && this.state.pendingQuestion !== 'brand_asked') {
        this.state.pendingQuestion = 'brand';
        this.state.step = 'ASKING_SPECS';
        let prompt = prefixMessage ? `${prefixMessage}\n\n` : '';
        prompt += `Sure! Do you have a preferred brand for ${this.formatName(this.state.category)}?`;
        return {
          reply: prompt,
          products: []
        };
      }

      // Question B: Budget (if user hasn't provided a budget at all yet)
      if (this.state.budget.raw_amount === null && this.state.pendingQuestion !== 'budget_asked') {
        this.state.pendingQuestion = 'budget';
        this.state.step = 'ASKING_SPECS';
        let prompt = prefixMessage ? `${prefixMessage}\n\n` : '';
        prompt += `What is your maximum budget for the ${this.formatName(this.state.category)}?`;
        return {
          reply: prompt,
          products: []
        };
      }

      // If user provided brand & budget (or skipped them) and 2-5 items match:
      let replyMsg = prefixMessage ? `${prefixMessage}\n\n` : '';
      replyMsg += `I found ${matches.length} ${this.formatName(this.state.category)} matching your requirements:`;

      return {
        reply: replyMsg,
        products: matches
      };
    }

    // SCENARIO 3: Zero Matches Found!
    const diagnosis = this.filterEngine.diagnoseZeroResults(this.state);
    const similar = this.filterEngine.getSimilarProducts(this.state);

    let replyMsg = prefixMessage ? `${prefixMessage}\n\n` : '';
    replyMsg += diagnosis;

    return {
      reply: replyMsg,
      followUp: "Would you like to change your budget or another specification?",
      noMatch: true,
      options: [
        this.state.brand ? 'Remove Brand Filter' : null,
        this.state.budget.confirmed ? 'Change Budget' : null,
        'Show Similar Products',
        'Start New Search'
      ].filter(Boolean),
      similarProducts: similar,
      products: []
    };
  }

  formatName(str) {
    if (!str) return '';
    return str.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ');
  }
}

// UI Controller
const ChatbotApp = {
  assistant: null,
  isOpen: false,

  init(catalog) {
    this.assistant = new ChatbotAssistant(catalog);
    this.renderUI();
  },

  renderUI() {
    if (document.getElementById('chatbotLauncher')) return;

    // 1. Floating Launcher Button
    const launcher = document.createElement('button');
    launcher.id = 'chatbotLauncher';
    launcher.className = 'fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-gradient-to-r from-indigo-600 to-violet-600 text-white shadow-xl hover:shadow-2xl hover:scale-105 active:scale-95 transition-all duration-200 flex items-center justify-center focus:outline-none focus:ring-4 focus:ring-indigo-200';
    launcher.setAttribute('aria-label', 'Open AI Product Search Assistant');
    launcher.innerHTML = `
      <div class="relative flex items-center justify-center">
        <svg id="launcherOpenIcon" class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        <svg id="launcherCloseIcon" class="w-7 h-7 hidden" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
        <span class="absolute -top-1 -right-1 flex h-3 w-3">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span class="relative inline-flex rounded-full h-3 w-3 bg-emerald-500 border-2 border-white"></span>
        </span>
      </div>
    `;

    // 2. Chat Window Container
    const chatWindow = document.createElement('div');
    chatWindow.id = 'chatbotWindow';
    chatWindow.className = 'fixed bottom-24 right-6 z-50 w-[380px] sm:w-[420px] max-w-[calc(100vw-2rem)] h-[580px] max-h-[calc(100vh-7rem)] bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden hidden transition-all duration-200 transform scale-95 opacity-0';

    chatWindow.innerHTML = `
      <!-- Header -->
      <div class="bg-gradient-to-r from-indigo-600 to-violet-600 px-4 py-3.5 text-white flex items-center justify-between shrink-0 shadow-sm">
        <div class="flex items-center gap-2.5">
          <div class="w-8 h-8 rounded-lg bg-white/20 backdrop-blur-sm flex items-center justify-center font-bold text-sm">
            AI
          </div>
          <div>
            <h3 class="font-bold text-sm leading-tight">Product Search Assistant</h3>
            <div class="flex items-center gap-1.5 text-[11px] text-indigo-100">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
              <span>Mist AI &bull; LLM Connected</span>
            </div>
          </div>
        </div>
        <div class="flex items-center gap-1">
          <button id="chatbotRestartBtn" title="Start New Search" class="p-1.5 text-indigo-100 hover:text-white hover:bg-white/10 rounded-lg transition">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>
          <button id="chatbotCloseBtn" title="Close" class="p-1.5 text-indigo-100 hover:text-white hover:bg-white/10 rounded-lg transition">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <!-- Messages Thread -->
      <div id="chatbotMessages" class="flex-1 p-4 overflow-y-auto space-y-3.5 bg-slate-50 text-xs">
        <!-- Chat bubbles rendered here -->
      </div>

      <!-- Input Area -->
      <form id="chatbotForm" class="p-2.5 bg-white border-t border-slate-200 flex items-center gap-2 shrink-0">
        <input 
          type="text" 
          id="chatbotInput" 
          placeholder="Type your answer (e.g. 'I want a laptop')..." 
          autocomplete="off"
          class="flex-1 text-xs bg-slate-100 border border-transparent rounded-xl px-3.5 py-2.5 outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-slate-800 transition"
        />
        <button 
          type="submit" 
          id="chatbotSendBtn"
          class="w-9 h-9 rounded-xl bg-indigo-600 text-white flex items-center justify-center hover:bg-indigo-700 active:scale-95 transition"
        >
          <svg class="w-4 h-4 transform rotate-90" fill="currentColor" viewBox="0 0 20 20">
            <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
          </svg>
        </button>
      </form>
    `;

    document.body.appendChild(launcher);
    document.body.appendChild(chatWindow);

    this.bindEvents();
  },

  bindEvents() {
    const launcher = document.getElementById('chatbotLauncher');
    const chatWindow = document.getElementById('chatbotWindow');
    const closeBtn = document.getElementById('chatbotCloseBtn');
    const restartBtn = document.getElementById('chatbotRestartBtn');
    const form = document.getElementById('chatbotForm');
    const input = document.getElementById('chatbotInput');

    const toggleChat = () => {
      this.isOpen = !this.isOpen;
      const openIcon = document.getElementById('launcherOpenIcon');
      const closeIcon = document.getElementById('launcherCloseIcon');

      if (this.isOpen) {
        chatWindow.classList.remove('hidden');
        setTimeout(() => {
          chatWindow.classList.remove('scale-95', 'opacity-0');
          chatWindow.classList.add('scale-100', 'opacity-100');
          input.focus();
        }, 10);
        openIcon.classList.add('hidden');
        closeIcon.classList.remove('hidden');

        const msgs = document.getElementById('chatbotMessages');
        if (msgs.children.length === 0) {
          this.triggerInitialGreeting();
        }
      } else {
        chatWindow.classList.add('scale-95', 'opacity-0');
        chatWindow.classList.remove('scale-100', 'opacity-100');
        setTimeout(() => {
          chatWindow.classList.add('hidden');
        }, 200);
        openIcon.classList.remove('hidden');
        closeIcon.classList.add('hidden');
      }
    };

    launcher.addEventListener('click', toggleChat);
    closeBtn.addEventListener('click', toggleChat);

    restartBtn.addEventListener('click', () => {
      this.assistant.reset();
      this.serverState = null;
      this.chatHistory = [];
      const msgs = document.getElementById('chatbotMessages');
      msgs.innerHTML = '';
      this.triggerInitialGreeting();
    });

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) return;

      this.addUserMessage(text);
      input.value = '';

      this.showTypingIndicator();

      let handledByBackend = false;

      // When running on HTTP server, send request to Mist AI backend
      if (typeof window !== 'undefined' && window.location && window.location.protocol.startsWith('http')) {
        try {
          if (!this.chatHistory) this.chatHistory = [];
          this.chatHistory.push({ role: 'user', content: text });

          const res = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              message: text,
              history: this.chatHistory.slice(-6),
              state: this.serverState || null,
              category: this.assistant ? this.assistant.state.category : null,
              brand: this.assistant ? this.assistant.state.brand : null,
              max_price: (this.assistant && this.assistant.state.budget && this.assistant.state.budget.confirmed) ? this.assistant.state.budget.usd_amount : null
            })
          });

          if (res.ok) {
            const data = await res.json();
            this.serverState = data.state;
            this.chatHistory.push({ role: 'assistant', content: data.reply });

            let chips = data.chips || [];
            if (!data.is_exact_match && data.products && data.products.length > 0 && chips.length === 0) {
              chips = ['Start New Search'];
            }

            this.hideTypingIndicator();
            this.addAssistantResponse({
              reply: data.reply,
              products: data.products || [],
              modelUsed: data.model_used,
              isExactMatch: data.is_exact_match,
              relaxedSpec: data.relaxed_spec,
              chips: chips
            });
            handledByBackend = true;
          }
        } catch (err) {
          console.warn("Backend /api/chat error, falling back to local engine:", err);
        }
      }

      if (!handledByBackend) {
        this.hideTypingIndicator();
        const response = this.assistant.processMessage(text);
        this.addAssistantResponse(response);
      }
    });
  },

  triggerInitialGreeting() {
    this.addAssistantResponse({
      reply: "Hello! What item or product are you looking for today?"
    });
  },

  addUserMessage(text) {
    const container = document.getElementById('chatbotMessages');
    const div = document.createElement('div');
    div.className = 'flex justify-end';
    div.innerHTML = `
      <div class="bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-3.5 py-2 max-w-[82%] shadow-sm leading-relaxed text-xs">
        ${this.escapeHTML(text)}
      </div>
    `;
    container.appendChild(div);
    this.scrollToBottom();
  },

  addAssistantResponse(resp) {
    const container = document.getElementById('chatbotMessages');
    const div = document.createElement('div');
    div.className = 'flex flex-col space-y-2 items-start';

    let contentHTML = `
      <div class="bg-white border border-slate-200 text-slate-800 rounded-2xl rounded-tl-sm p-3 max-w-[92%] shadow-sm leading-relaxed space-y-2">
        <div class="font-medium whitespace-pre-line">${this.formatMarkdown(resp.reply)}</div>
        ${resp.followUp ? `<p class="text-indigo-700 font-semibold mt-1">${this.formatMarkdown(resp.followUp)}</p>` : ''}
    `;

    // Render Action Chips / Quick Selection Buttons (e.g. [PKR] [USD], [Yes, use this budget])
    if (resp.chips && resp.chips.length > 0) {
      contentHTML += `
        <div class="pt-2 flex flex-wrap gap-1.5">
          ${resp.chips.map(chip => `
            <button class="chat-chip-btn text-[11px] font-semibold bg-indigo-50 text-indigo-700 px-3 py-1 rounded-lg hover:bg-indigo-100 border border-indigo-200 transition" data-text="${chip}">
              ${chip}
            </button>
          `).join('')}
        </div>
      `;
    }

    // Render single product match (Strict Single-Product Rule: max 1 product card)
    if (resp.isSingleMatch && resp.product) {
      contentHTML += this.renderSingleProductCard(resp.product);
    } else if (resp.products && resp.products.length > 0) {
      contentHTML += this.renderSingleProductCard(resp.products[0]);
    }

    // Render Zero Match Recovery Options (No alternative products per Rule 8, 9, 10)
    if (resp.noMatch && resp.options) {
      contentHTML += `
        <div class="pt-2 border-t border-slate-100 space-y-1.5">
          <p class="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Suggested Actions:</p>
          <div class="flex flex-wrap gap-1.5">
            ${resp.options.map(opt => `
              <button class="chat-action-btn text-[11px] font-semibold bg-slate-100 text-slate-700 px-2.5 py-1 rounded-lg hover:bg-slate-200 border border-slate-200 transition" data-action="${opt}">
                ${opt}
              </button>
            `).join('')}
          </div>
        </div>
      `;
    }

    contentHTML += `</div>`;
    div.innerHTML = contentHTML;
    container.appendChild(div);

    // Event listeners
    div.querySelectorAll('.chat-chip-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const text = btn.dataset.text;
        document.getElementById('chatbotInput').value = text;
        document.getElementById('chatbotForm').dispatchEvent(new Event('submit'));
      });
    });

    div.querySelectorAll('.chat-product-card').forEach(card => {
      card.addEventListener('click', () => {
        const id = card.dataset.productId;
        const p = this.assistant.catalog.find(item => String(item.id) === String(id));
        if (p && typeof window.openModal === 'function') {
          window.openModal(p);
        }
      });
    });

    div.querySelectorAll('.chat-action-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        document.getElementById('chatbotInput').value = action;
        document.getElementById('chatbotForm').dispatchEvent(new Event('submit'));
      });
    });

    this.scrollToBottom();
  },

  renderSingleProductCard(p) {
    const thumb = p.thumbnail || p.image || (p.images && p.images[0]) || '';
    const price = typeof p.price === 'number' ? `$${p.price.toFixed(2)}` : `$${p.price}`;
    const rating = typeof p.rating === 'number' ? p.rating.toFixed(1) : (p.rating && p.rating.rate ? p.rating.rate.toFixed(1) : '4.5');

    return `
      <div class="chat-product-card mt-2 p-3 rounded-xl bg-slate-50 border border-slate-200/90 shadow-xs cursor-pointer hover:border-indigo-400 transition" data-product-id="${p.id}">
        <div class="flex items-center gap-3">
          <img src="${thumb}" alt="${p.title}" class="w-16 h-16 rounded-lg object-contain bg-white p-1 border border-slate-100 shrink-0" onerror="this.src='https://via.placeholder.com/80?text=Product'">
          <div class="flex-1 min-w-0">
            <h4 class="font-bold text-xs text-slate-900 truncate">${p.title}</h4>
            <div class="text-[11px] text-slate-500 mt-0.5">
              <span>Brand: <strong>${p.brand || 'N/A'}</strong></span> &bull; <span>${p.category}</span>
            </div>
            <div class="flex items-center justify-between mt-1">
              <span class="text-sm font-bold text-slate-900">${price} USD ${p.price_pkr ? `<span class="text-xs text-indigo-700 font-medium">(~Rs. ${p.price_pkr.toLocaleString()} PKR)</span>` : ''}</span>
              <span class="text-[11px] font-semibold text-amber-600">★ ${rating}</span>
            </div>
          </div>
        </div>

        <div class="mt-2 pt-2 border-t border-slate-200/60 grid grid-cols-2 gap-1.5 text-[10px] text-slate-600">
          ${p.warrantyInformation ? `<div>Warranty: <strong>${p.warrantyInformation}</strong></div>` : ''}
          ${p.availabilityStatus ? `<div>Status: <strong>${p.availabilityStatus}</strong></div>` : ''}
          ${p.shippingInformation ? `<div class="col-span-2">Shipping: ${p.shippingInformation}</div>` : ''}
        </div>

        <button class="w-full mt-2.5 py-1.5 text-center text-xs font-semibold text-indigo-700 bg-white border border-indigo-200 rounded-lg hover:bg-indigo-600 hover:text-white transition">
          View Product Details
        </button>
      </div>
    `;
  },

  renderMultipleProductCards(products) {
    let html = `<div class="space-y-2 mt-2 max-h-72 overflow-y-auto pr-1">`;
    products.slice(0, 5).forEach(p => {
      const thumb = p.thumbnail || p.image || (p.images && p.images[0]) || '';
      const price = typeof p.price === 'number' ? `$${p.price.toFixed(2)}` : `$${p.price}`;
      const rating = typeof p.rating === 'number' ? p.rating.toFixed(1) : (p.rating && p.rating.rate ? p.rating.rate.toFixed(1) : '4.5');

      html += `
        <div class="chat-product-card flex items-center gap-2.5 p-2 rounded-xl bg-slate-50 hover:bg-indigo-50/60 border border-slate-200/80 cursor-pointer transition group" data-product-id="${p.id}">
          <img src="${thumb}" alt="${p.title}" class="w-12 h-12 rounded-lg object-contain bg-white p-1 border border-slate-100 shrink-0" onerror="this.src='https://via.placeholder.com/60?text=Product'">
          <div class="flex-1 min-w-0">
            <h4 class="font-bold text-[11px] text-slate-800 truncate group-hover:text-indigo-600 transition">${p.title}</h4>
            <div class="flex items-center gap-2 text-[10px] text-slate-500 mt-0.5">
              <span>${p.brand || 'Item'}</span>
              <span>&bull;</span>
              <span class="text-amber-600 font-semibold">★ ${rating}</span>
            </div>
            <div class="text-[11px] font-bold text-slate-900 mt-0.5">${price} USD ${p.price_pkr ? `<span class="text-[10px] text-indigo-600 font-normal">(~Rs. ${p.price_pkr.toLocaleString()})</span>` : ''}</div>
          </div>
          <button class="text-[10px] font-semibold text-indigo-600 bg-white border border-indigo-200 px-2 py-1 rounded-md shadow-xs group-hover:bg-indigo-600 group-hover:text-white transition shrink-0">
            View
          </button>
        </div>
      `;
    });
    if (products.length > 5) {
      html += `<div class="text-center text-[10px] text-slate-400 font-medium py-1">+ ${products.length - 5} more products</div>`;
    }
    html += `</div>`;
    return html;
  },

  showTypingIndicator() {
    const container = document.getElementById('chatbotMessages');
    const div = document.createElement('div');
    div.id = 'chatbotTypingIndicator';
    div.className = 'flex items-center gap-1.5 bg-white border border-slate-200 px-3 py-2 rounded-2xl rounded-tl-sm w-16 shadow-xs';
    div.innerHTML = `
      <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-bounce"></span>
      <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-bounce" style="animation-delay: 0.15s"></span>
      <span class="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-bounce" style="animation-delay: 0.3s"></span>
    `;
    container.appendChild(div);
    this.scrollToBottom();
  },

  hideTypingIndicator() {
    const indicator = document.getElementById('chatbotTypingIndicator');
    if (indicator) indicator.remove();
  },

  scrollToBottom() {
    const container = document.getElementById('chatbotMessages');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  },

  formatMarkdown(text) {
    if (!text) return '';
    return text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  },

  escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag));
  }
};

if (typeof window !== 'undefined') {
  window.ChatbotApp = ChatbotApp;
}

// Browser Initialization
if (typeof window !== 'undefined' && typeof window.addEventListener === 'function') {
  window.addEventListener('DOMContentLoaded', () => {
    if (window.PRODUCTS_DATA && Array.isArray(window.PRODUCTS_DATA)) {
      ChatbotApp.init(window.PRODUCTS_DATA);
    } else {
      const checkInterval = setInterval(() => {
        if (window.PRODUCTS_DATA && Array.isArray(window.PRODUCTS_DATA)) {
          clearInterval(checkInterval);
          ChatbotApp.init(window.PRODUCTS_DATA);
        }
      }, 100);
    }
  });
}

// Node.js module export (for testing)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    CurrencyManager,
    CatalogAnalyzer,
    RuleBasedParser,
    ProductFilterEngine,
    ChatbotAssistant
  };
}
