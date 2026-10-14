package com.cloudstreamid.__PKG__

import android.content.Context
import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin

@CloudstreamPlugin
class __NAME__Plugin : Plugin() {
    override fun load(context: Context) {
        registerMainAPI(__NAME__Provider())
    }
}
