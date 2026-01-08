const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

// تحديث الرابط المستهدف للموقع الجديد
const targetUrl = 'https://www.novel543.com/1227676079/8095_1128.html';

async function scrapeWithFinalSolution() {
    try {
        console.log(`[LOG] محاولة جلب البيانات من الموقع الجديد عبر جسر Proxy...`);

        // استخدام خدمة Proxy لتغيير الـ IP وضمان الوصول
        const bridgeUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(targetUrl)}`;

        const response = await axios.get(bridgeUrl, { timeout: 30000 });

        if (!response.data || !response.data.contents) {
            throw new Error("لم يتم الحصول على استجابة من جسر الـ Proxy.");
        }

        const htmlContent = response.data.contents;
        const $ = cheerio.load(htmlContent);

        // --- تحديث الاستخراج ليتناسب مع الموقع الجديد ---
        
        // 1. استخراج العنوان (موجود داخل h1 في الموقع الجديد)
        const title = $('.chapter-content h1').text().trim();

        if (!title) {
            throw new Error("فشل استخراج العنوان. قد تكون هيكلية الصفحة مختلفة أو هناك حظر.");
        }

        // 2. تنظيف المحتوى (إزالة الإعلانات والوسوم غير المرغوبة داخل المحتوى)
        // الموقع الجديد يضع النص داخل div.content
        $('.content.py-5 .gadBlock, .content.py-5 .adBlock, .content.py-5 script, .content.py-5 div').remove();
        
        let content = $('.content.py-5').text();
        
        // 3. تنظيف النصوص من الفراغات والرموز الزائدة
        content = content
            .replace(/\t/g, '')
            .replace(/\n\s*\n/g, '\n\n')
            .trim();

        // 4. استخراج رابط الفصل التالي
        // الموقع الجديد يضع الروابط في متغيرات js أو في أزرار التنقل تحت اسم "下一章"
        const nextUrl = $('.foot-nav a:contains("下一章")').attr('href');
        const fullNextUrl = nextUrl ? (nextUrl.startsWith('http') ? nextUrl : `https://www.novel543.com${nextUrl}`) : null;

        console.log(`[SUCCESS] تم جلب الفصل بنجاح: ${title}`);
        
        return {
            status: 'success',
            data: {
                title,
                nextChapter: fullNextUrl,
                content: content // إرسال النص كاملاً
            }
        };

    } catch (error) {
        console.error(`[ERROR] ${error.message}`);
        return {
            status: 'error',
            message: `فشل تجاوز الحماية أو استخراج البيانات: ${error.message}`,
            suggestion: "تأكد من أن روابط الموقع لا تزال تعمل، أو جرب تحديث الـ Selectors إذا قام الموقع بتغيير تصميمه."
        };
    }
}

const http = require('http');
const server = http.createServer(async (req, res) => {
    // دعم اللغة العربية والصينية في الاستجابة
    res.setHeader('Content-Type', 'application/json; charset=utf-8');

    if (req.url === '/test') {
        const result = await scrapeWithFinalSolution();
        res.writeHead(200);
        res.end(JSON.stringify(result, null, 2));
    } else {
        res.writeHead(200);
        res.end(JSON.stringify({ 
            status: 'Novel543 Scraper Active',
            endpoint: '/test',
            note: 'Current target: https://www.novel543.com'
        }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
