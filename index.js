const axios = require('axios');
const cheerio = require('cheerio');
const iconv = require('iconv-lite');

const targetUrl = 'https://www.69shuba.com/txt/87906/39867326';

async function scrapeWithFinalSolution() {
    try {
        console.log(`[LOG] محاولة الجلب عبر جسر Proxy لتجاوز حظر الـ IP...`);

        // استخدام خدمة Proxy مجانية تماماً لتغيير الـ IP الخاص بـ Railway
        // سنطلب البيانات بصيغة Base64 لتجنب مشاكل الترميز الصيني
        const bridgeUrl = `https://api.allorigins.win/get?url=${encodeURIComponent(targetUrl)}`;

        const response = await axios.get(bridgeUrl, { timeout: 30000 });

        if (!response.data || !response.data.contents) {
            throw new Error("لم يتم الحصول على استجابة من جسر الـ Proxy.");
        }

        // معالجة البيانات القادمة من الجسر
        const htmlContent = response.data.contents;
        const $ = cheerio.load(htmlContent);

        // استخراج العنوان
        const title = $('h1').last().text().trim();

        if (!title) {
            // إذا لم نجد عنواناً، فهذا يعني أن الجسر نفسه قد يكون محظوراً أو الصفحة لم تُحمل
            throw new Error("فشل استخراج البيانات. قد يكون الموقع قد حظر الجسر أيضاً.");
        }

        // تنظيف المحتوى
        $('.txtnav script, .txtnav .contentadv, .txtnav .txtinfo, .txtnav h1').remove();
        let content = $('.txtnav').text();
        
        // تنظيف النصوص
        content = content
            .replace(/\t/g, '')
            .replace(/\(本章完\)/g, '')
            .replace(/\n\s*\n/g, '\n\n')
            .trim();

        const nextUrl = $('.page1 a:contains("下一章")').attr('href') || 
                        $('.page1 a').last().attr('href');

        console.log(`[SUCCESS] نجحت الخطة! تم كسر الحظر وجلب الفصل: ${title}`);
        
        return {
            status: 'success',
            data: {
                title,
                nextChapter: nextUrl,
                content: content.substring(0, 1000) // إرسال أول 1000 حرف
            }
        };

    } catch (error) {
        console.error(`[ERROR] ${error.message}`);
        return {
            status: 'error',
            message: `فشل تجاوز الحماية: ${error.message}`,
            suggestion: "الموقع محمي بشدة، قد نحتاج لاستخدام بروكسي مدفوع أو العودة لمتصفح Puppeteer رغم استهلاكه للموارد."
        };
    }
}

const http = require('http');
const server = http.createServer(async (req, res) => {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');

    if (req.url === '/test') {
        const result = await scrapeWithFinalSolution();
        res.writeHead(200);
        res.end(JSON.stringify(result, null, 2));
    } else {
        res.writeHead(200);
        res.end(JSON.stringify({ 
            status: 'Proxy Bridge Mode Active',
            endpoint: '/test',
            note: 'Using external bridge to bypass 403 error.'
        }));
    }
});

const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});
