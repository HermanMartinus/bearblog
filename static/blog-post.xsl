<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="html" indent="yes"/>
  
  <xsl:template match="/">
    <html>
      <head>
        <title><xsl:value-of select="post/title"/></title>
        <link rel="stylesheet" type="text/css" href="/static/styles.css"/>
      </head>
      <body>
        <div class="container">
          <header>
            <div id="branding">
              <h1>My Blog</h1>
            </div>
            <nav>
              <ul>
                <li><a href="/">Home</a></li>
                <li><a href="/about">About</a></li>
                <li><a href="/contact">Contact</a></li>
              </ul>
            </nav>
          </header>
          
          <main>
            <article>
              <h1><xsl:value-of select="post/title"/></h1>
              <p class="meta">Published on <xsl:value-of select="post/date"/></p>
              <div class="content">
                <xsl:value-of select="post/content" disable-output-escaping="yes"/>
              </div>
            </article>
          </main>
          
          <aside id="sidebar">
            <h3>Categories</h3>
            <ul>
              <li><a href="#">Web Development</a></li>
              <li><a href="#">Design</a></li>
              <li><a href="#">Technology</a></li>
            </ul>
          </aside>
          
          <footer>
            <p>Copyright &copy; 2023 My Blog</p>
          </footer>
        </div>
      </body>
    </html>
  </xsl:template>
</xsl:stylesheet>